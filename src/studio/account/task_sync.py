import mimetypes
import time
from queue import Queue
from threading import Thread, Lock
from typing import Callable, Optional, TYPE_CHECKING

from .task_history import (
    TaskStatus,
    TaskStatusData,
    TaskHistoryData,
    AccountTaskHistory,
)
from .network import get_session
from ..utils import save_mime_typed_datas_to_temp_files
from ...logger import logger

if TYPE_CHECKING:
    from .core import Account


class StatusResponseParser:
    """状态查询响应解析器

    处理后端状态查询接口返回的数据，格式为：
    {
        "responseId": "2009467300415012864",
        "code": 1000,
        "data": {
            "taskId": {
                "state": "completed",
                "urls": ["https://xxxxx", "https://yyyyy"]
            }
        }
    }
    """

    def parse_batch_response(self, response_json: dict) -> dict[str, TaskStatusData]:
        result = {}
        data = response_json.get("data", {})
        print("response_json",response_json)
        print("parse_batch_response")
        for task_id, task_info in data.items():
            print(f"\t{task_id}:{task_info}")
            print()
            state = TaskStatus(task_info.get("state", TaskStatus.UNKNOWN.value))
            urls = task_info.get("urls") or []
            progress = 1.0 if state == TaskStatus.SUCCESS else 0.0
            error_message = task_info.get("msg")

            result[task_id] = TaskStatusData(
                task_id=task_id,
                state=state,
                urls=urls,
                progress=progress,
                error_message=error_message,
            )
        print()
        print()

        return result

    def download_result(self, urls: list[str]) -> list[tuple[str, bytes]]:
        # TODO 是否考虑在下一次轮询前未下载完成时, 是否会导致重复下载?
        results = []
        for url in urls:
            logger.info(f"Downloading result from: {url}")
            session = get_session()
            response = session.get(url)
            response.raise_for_status()
            results.append((url, response.content))
        return results

    def convert_to_unified_format(self, parsed_data: list[tuple[str, bytes]]) -> list[tuple[str, bytes]]:
        results = []
        for url, data in parsed_data:
            mime_type = self._detect_mime_type(url, data)
            results.append((mime_type, data))
        return results

    def _detect_mime_type(self, url: str, data: bytes) -> str:
        # 1. 尝试从 URL 后缀推断
        mime_type = mimetypes.guess_type(url)[0]
        if mime_type:
            return mime_type

        # 2. 尝试从数据头推断
        if data.startswith(b"\x89PNG"):
            return "image/png"
        elif data.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        elif data.startswith(b"RIFF") and b"WEBP" in data[:12]:
            return "image/webp"

        # 3. 默认返回 PNG
        return "image/png"


class TaskSyncService:
    """任务同步服务

    职责：
    - 批量查询后端任务状态
    - 解析状态响应
    - 下载并保存结果文件
    - 更新 History 记录
    - 通过回调通知上层（解耦 Blender 操作）
    - 防止并发重复同步（主动查询 vs 定时轮询）
    """

    def __init__(self, account: "Account", task_history: "AccountTaskHistory"):
        self.account = account
        self.task_history = task_history
        self.parser = StatusResponseParser()
        self.result_callback: Optional[Callable[[TaskHistoryData], None]] = None

        self._syncing_task_ids: set[str] = set()
        self._sync_lock = Lock()

    def set_result_callback(self, callback: Callable[[TaskHistoryData], None]):
        """设置结果回调函数

        当任务完成下载后，会调用此回调通知上层。
        这允许上层（如 Studio）决定如何处理结果（例如加载到 Blender）。

        Args:
            callback: 回调函数，接收 TaskHistoryData 参数
        """
        self.result_callback = callback

    def sync_tasks(self, task_ids: list[str]) -> int:
        if not task_ids:
            return 0

        #  过滤掉已在同步中的任务
        with self._sync_lock:
            available_task_ids = [tid for tid in task_ids if tid not in self._syncing_task_ids]
            if not available_task_ids:
                return 0

            self._syncing_task_ids.update(available_task_ids)  # 标记为同步中

        try:
            # 1. 查询后端状态
            logger.info(f"Querying status of {len(available_task_ids)} tasks...")
            response_json = self.account._fetch_task_status(available_task_ids)

            # 2. 解析响应
            status_map = self.parser.parse_batch_response(response_json)

            # 3. 更新每个任务
            success_count = 0
            for task_id in available_task_ids:
                task_history = self.task_history.ensure_task_history(task_id)
                if task_id in status_map:
                    if self._update_single_task(task_history, status_map[task_id]):
                        success_count += 1
                else:
                    # 任务不在响应中，标记为不存在
                    self._mark_task_not_found(task_history)

            logger.info(f"Successfully synced {success_count}/{len(available_task_ids)} tasks")
            return success_count

        except Exception as e:
            logger.error(f"Failed to sync task status: {e}")
            return 0

        finally:
            # 移除标记
            with self._sync_lock:
                self._syncing_task_ids.difference_update(available_task_ids)

    def sync_single_task(self, task_id: str) -> bool:
        return self.sync_tasks([task_id]) > 0

    def _update_single_task(self, task_history: TaskHistoryData, status: TaskStatusData) -> bool:
        try:
            if status.state.is_success():
                self._handle_completed_task(task_history, status)
            elif status.state.is_running():
                self._handle_processing_task(task_history, status)
            elif status.state.is_failed():
                self._handle_failed_task(task_history, status)
            elif status.state.is_unknown():
                self._handle_not_found_task(task_history, status)
            return True
        except Exception as e:
            logger.error(f"Failed to update task {task_history.task_id}: {e}")
            task_history.error_message = f"Status sync failed: {str(e)}"
            task_history.finished_at = time.time()
            task_history.state = TaskStatus.ERROR
            task_history.progress = 0.0
            return False

    def _handle_completed_task(self, task_history: TaskHistoryData, status: TaskStatusData):
        logger.info(f"Task {task_history.task_id} completed, downloading result...")

        # 下载结果
        data = self.parser.download_result(status.urls)

        # 转换为统一格式
        parsed_data = self.parser.convert_to_unified_format(data)

        # 保存文件（需要导入 utils）
        outputs = save_mime_typed_datas_to_temp_files(parsed_data)

        # 更新 History
        task_history.state = TaskStatus.SUCCESS
        task_history.outputs = outputs
        task_history.result = parsed_data
        task_history.error_message = ""
        task_history.finished_at = time.time()
        task_history.progress = 1.0

        logger.info(f"Task {task_history.task_id} result synchronized")

        # 通知上层（回调）
        if self.result_callback:
            self.result_callback(task_history)

    def _handle_processing_task(self, task_history: TaskHistoryData, status: TaskStatusData):
        logger.info(f"Task {task_history.task_id} is running")
        task_history.state = TaskStatus.RUNNING
        task_history.error_message = ""
        task_history.progress = status.progress

    def _handle_failed_task(self, task_history: TaskHistoryData, status: TaskStatusData):
        logger.warning(f"Task {task_history.task_id} failed in backend")
        task_history.state = TaskStatus.FAILED
        task_history.error_message = status.error_message
        task_history.finished_at = time.time()
        task_history.progress = 0.0

    def _handle_not_found_task(self, task_history: TaskHistoryData, status: TaskStatusData):
        logger.warning(f"Task {task_history.task_id} not found in backend")
        task_history.state = TaskStatus.UNKNOWN
        task_history.error_message = status.error_message
        task_history.progress = 0.0

    def _mark_task_not_found(self, task_history: TaskHistoryData):
        pass  # 预留方法，目前不需要特殊处理


class TaskStatusPoller:
    """任务状态轮询器

    定期扫描待同步的任务，调用同步服务更新状态。
    """

    def __init__(self, account: "Account", sync_service: "TaskSyncService", interval: float = 10.0):
        self.account = account
        self.sync_service = sync_service
        self.interval = interval
        self.running = False
        self.thread = None
        self.pending_task_ids: Queue[str] = Queue()

    def add_pending_task_ids(self, task_ids: list[str]):
        for task_id in task_ids:
            self.pending_task_ids.put(task_id)

    def get_pending_task_ids(self) -> list[str]:
        ids = []
        if self.pending_task_ids.empty():
            return []
        while not self.pending_task_ids.empty():
            ids.append(self.pending_task_ids.get())
        return list(set(ids))

    def start(self):
        if self.running:
            logger.warning("Poller is already running")
            return

        self.running = True
        self.thread = Thread(target=self._polling_loop, daemon=True, name="TaskStatusPoller")
        self.thread.start()
        logger.info(f"Task status poller started (interval: {self.interval} seconds)")

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
        logger.info("Task status poller stopped")

    def _polling_loop(self):
        while self.running:
            try:
                self._poll_once()
            except Exception as e:
                logger.error(f"Error during polling: {e}")

            # 分段休眠，以便快速响应停止信号
            for _ in range(int(self.interval * 4)):
                if not self.running:
                    break
                time.sleep(0.25)

    def _poll_once(self):
        # 找出所有需要同步状态的任务
        task_ids: list[str] = self.get_pending_task_ids()

        if not task_ids:
            return

        logger.info(f"{len(task_ids)} tasks to sync")

        # 调用同步服务
        self.sync_service.sync_tasks(task_ids)
