import time
import requests
import mimetypes
from enum import Enum
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
from dataclasses import dataclass
from threading import Thread
from typing import Optional, Dict, List, Tuple
from ..base import StudioHistoryItem, StudioHistory
from ...account import Account
from ...utils import save_mime_typed_datas_to_temp_files, load_images_into_blender
from ....logger import logger


class TaskStatus(Enum):
    NONE = "NONE"
    SUCCESS = "SUCCESS"
    RUNNING = "RUNNING"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


@dataclass
class TaskStatusData:
    """任务状态数据"""

    task_id: str
    state: TaskStatus = TaskStatus.NONE
    urls: Optional[list[str]] = None  # 结果下载地址
    progress: float = 0.0
    error_message: str = ""

    def is_success(self) -> bool:
        return self.state == TaskStatus.SUCCESS

    def is_running(self) -> bool:
        return self.state == TaskStatus.RUNNING

    def is_failed(self) -> bool:
        return self.state == TaskStatus.FAILED

    def is_unknown(self) -> bool:
        return self.state == TaskStatus.UNKNOWN


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

    def parse_batch_response(self, response_json: dict) -> Dict[str, TaskStatusData]:
        result = {}

        code = response_json.get("code")
        if code != 1000:
            logger.warning(f"Status query returned non-success code: {code}")
            return result

        data = response_json.get("data", {})

        for task_id, task_info in data.items():
            state = TaskStatus(task_info.get("state", TaskStatus.UNKNOWN.value))
            urls = task_info.get("urls")
            error_message = task_info.get("msg")

            progress = 1.0 if state == TaskStatus.SUCCESS else 0.0

            result[task_id] = TaskStatusData(
                task_id=task_id,
                state=state,
                urls=urls,
                progress=progress,
                error_message=error_message,
            )

        return result

    def download_result(self, urls: list[str], timeout: int = 30, retry: int = 3) -> List[Tuple[str, bytes]]:
        results = []
        for url in urls:
            logger.info(f"Downloading result from: {url}")
            retry_strategy = Retry(
                total=retry,
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=["GET"],
                backoff_factor=0.5,
            )
            adapter = HTTPAdapter(max_retries=retry_strategy)
            session = requests.Session()
            session.mount("https://", adapter)
            session.mount("http://", adapter)
            response = session.get(url, timeout=timeout)
            response.raise_for_status()
            results.append((url, response.content))
        return results

    def convert_to_unified_format(self, parsed_data: list[Tuple[str, bytes]]) -> List[Tuple[str, bytes]]:
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


class TaskStatusSyncService:
    """任务状态同步服务

    职责：
    - 批量查询后端任务状态
    - 解析状态响应
    - 下载并保存结果文件
    - 更新 History 记录
    """

    def __init__(self, account: Account, history: StudioHistory):
        self.account: Account = account
        self.history: StudioHistory = history
        self.parser = StatusResponseParser()

    def sync_tasks(self, task_ids: List[str]) -> int:
        if not task_ids:
            return 0

        try:
            # 1. 查询后端状态
            logger.info(f"Querying status of {len(task_ids)} tasks...")
            response_json = self.account.fetch_task_status(task_ids)

            # 2. 解析响应
            status_map = self.parser.parse_batch_response(response_json)

            # 3. 更新每个任务
            success_count = 0
            for task_id in task_ids:
                if task_id in status_map:
                    if self._update_single_task(task_id, status_map[task_id]):
                        success_count += 1
                else:
                    # 任务不在响应中，标记为不存在
                    self._mark_task_not_found(task_id)

            logger.info(f"Successfully synced {success_count}/{len(task_ids)} tasks")
            return success_count

        except Exception as e:
            logger.error(f"Failed to sync task status: {e}")
            return 0

    def sync_single_task(self, task_id: str) -> bool:
        return self.sync_tasks([task_id]) > 0

    def _update_single_task(self, task_id: str, status: TaskStatusData) -> bool:
        item = self.history.find_by_task_id(task_id)
        if not item:
            logger.warning(f"History item for task {task_id} not found")
            return False

        try:
            if status.is_success():
                self._handle_completed_task(item, status)

            elif status.is_running():
                self._handle_processing_task(item, status)

            elif status.is_failed():
                self._handle_failed_task(item, status)

            elif status.is_unknown():
                self._handle_not_found_task(item, status)

            self.history.update_item(item)
            return True

        except Exception as e:
            logger.error(f"Failed to update task {task_id}: {e}")
            item.error_message = f"Status sync failed: {str(e)}"
            self.history.update_item(item)
            return False

    def _handle_completed_task(self, item: StudioHistoryItem, status: TaskStatusData):
        logger.info(f"Task {item.task_id} completed, downloading result...")

        # 下载结果
        data = self.parser.download_result(status.urls)

        # 转换为统一格式
        parsed_data = self.parser.convert_to_unified_format(data)

        # 保存文件
        outputs = save_mime_typed_datas_to_temp_files(parsed_data)

        # 更新 History
        item.status = StudioHistoryItem.STATUS_SUCCESS
        item.outputs = outputs
        item.result = parsed_data
        item.error_message = ""
        item.finished_at = time.time()
        item.progress = 1.0

        # 加载到 Blender
        load_images_into_blender(outputs)

        logger.info(f"Task {item.task_id} result synchronized")

    def _handle_processing_task(self, item: StudioHistoryItem, status: TaskStatusData):
        item.status = StudioHistoryItem.STATUS_PROCESSING
        item.progress = status.progress
        item.error_message = ""
        logger.info(f"Task {item.task_id} is running")

    def _handle_failed_task(self, item: StudioHistoryItem, status: TaskStatusData):
        item.status = StudioHistoryItem.STATUS_FAILED
        item.error_message = status.error_message or "Backend task execution failed"
        item.finished_at = time.time()
        logger.warning(f"Task {item.task_id} failed in backend")

    def _handle_not_found_task(self, item: StudioHistoryItem, status: TaskStatusData):
        item.status = StudioHistoryItem.STATUS_FAILED
        item.error_message = status.error_message or "Backend task not found (Expired or failed to submit due to network reason)"
        item.finished_at = time.time()
        logger.warning(f"Task {item.task_id} not found in backend")

    def _mark_task_not_found(self, task_id: str):
        item = self.history.find_by_task_id(task_id)
        if not item:
            return
        self._handle_not_found_task(item)
        self.history.update_item(item)


class TaskStatusPoller:
    """任务状态轮询器

    定期扫描 History 中状态为 UNKNOWN 的任务，调用同步服务更新状态
    """

    def __init__(self, account: Account, history: StudioHistory, interval: float = 10.0):
        self.account: Account = account
        self.history: StudioHistory = history
        self.interval = interval
        self.running = False
        self.thread = None
        self.sync_service = None

    def start(self):
        if self.running:
            logger.warning("Poller is already running")
            return

        self.running = True
        self.sync_service = TaskStatusSyncService(self.account, self.history)
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
        items_to_sync: list[StudioHistoryItem] = self.history.find_all_needs_status_sync_items()

        if not items_to_sync:
            return

        logger.info(f"Found {len(items_to_sync)} tasks to sync")

        # 批量查询
        task_ids = [item.task_id for item in items_to_sync]
        self.sync_service.sync_tasks(task_ids)
