import base64
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from threading import Thread, Lock
from typing import TYPE_CHECKING, Callable, Optional

from .network import get_session
from ..exception import (
    APIRequestException,
    AuthFailedException,
    InsufficientBalanceException,
    ParameterValidationException,
    ToeknExpiredException,
)

if TYPE_CHECKING:
    from .core import Account

try:
    from ...logger import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


class CTalkState(Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"

    def is_terminal(self) -> bool:
        return self in (CTalkState.SUCCESS, CTalkState.FAILED)

    def is_pending_or_running(self) -> bool:
        return self in (CTalkState.PENDING, CTalkState.RUNNING)


@dataclass
class CTalkStatusData:
    """CTalk 状态查询响应的单条记录（DTO）"""
    state: CTalkState = CTalkState.UNKNOWN
    content: str = ""
    msg: str = ""
    used_time: int = 0


@dataclass
class PromptReverseTask:
    """单个提示词反求任务"""
    req_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    state: CTalkState = CTalkState.PENDING
    content: str = ""
    error_message: str = ""
    created_at: float = field(default_factory=time.time)
    finished_at: float = 0.0
    callback: Optional[Callable[[str], None]] = field(default=None, repr=False)
    error_callback: Optional[Callable[[str], None]] = field(default=None, repr=False)

    def is_waiting(self) -> bool:
        return self.state.is_pending_or_running()

    def is_done(self) -> bool:
        return self.state.is_terminal()


# ==================== API 客户端 ====================


class CTalkApiClient:
    """CTalk API 网络客户端

    职责：
    - 提交 CTalk 对话请求（POST /service/ctalk）
    - 批量查询 CTalk 历史记录（GET /service/history-ctalk）
    - 统一的错误码解析
    """

    _ERROR_MAP = {
        ("余额不足",): InsufficientBalanceException,
        ("API请求错误!",): APIRequestException,
        ("鉴权错误",): AuthFailedException,
        ("Token过期",): ToeknExpiredException,
        ("参数校验错误",): ParameterValidationException,
    }

    def __init__(self, account: "Account"):
        self._account = account

    def _build_headers(self) -> dict:
        return {
            "X-Auth-T": self._account.token,
            "Content-Type": "application/json",
        }

    def _parse_error(self, err_msg: str) -> Optional[Exception]:
        if not err_msg:
            return None
        for keys, exc_cls in self._ERROR_MAP.items():
            if err_msg in keys:
                return exc_cls(err_msg)
        return APIRequestException(err_msg)

    def submit(self, image_base64: str, req_id: str, prompt: str = "") -> int:
        """提交 CTalk 对话请求

        Args:
            image_base64: 图片的 Base64 编码
            req_id: 请求 UUID
            prompt: 提示语（为空使用默认提示词）

        Returns:
            LogID

        Raises:
            各类 StudioException
        """
        url = f"{self._account.service_url}/service/ctalk"
        payload = {
            "imageBase64": image_base64,
            "reqId": req_id,
        }
        if prompt:
            payload["prompt"] = prompt

        session = get_session()
        resp = session.post(url, headers=self._build_headers(), json=payload, timeout=30)
        resp.raise_for_status()

        resp_json: dict = resp.json()
        code = resp_json.get("code", -1)
        err_msg = resp_json.get("errMsg", "")

        if code != 0:
            error = self._parse_error(err_msg)
            if error:
                raise error
            raise APIRequestException(f"CTalk submit failed: code={code}, msg={err_msg}")

        return resp_json.get("data", 0)

    def query_history(self, req_ids: list[str]) -> dict[str, CTalkStatusData]:
        """批量查询 CTalk 历史记录

        Args:
            req_ids: 请求 ID 列表

        Returns:
            {req_id: CTalkStatusData}
        """
        if not req_ids:
            return {}

        url = f"{self._account.service_url}/service/history-ctalk"
        payload = {"reqIds": req_ids}

        session = get_session()
        resp = session.get(url, headers=self._build_headers(), json=payload, timeout=10)
        resp.raise_for_status()

        resp_json: dict = resp.json()
        code = resp_json.get("code", -1)
        err_msg = resp_json.get("errMsg", "")

        if code != 0:
            error = self._parse_error(err_msg)
            if error:
                raise error
            raise APIRequestException(f"CTalk history query failed: code={code}, msg={err_msg}")

        result: dict[str, CTalkStatusData] = {}
        data: dict = resp_json.get("data", {})
        for req_id, info in data.items():
            try:
                state = CTalkState(info.get("state", "UNKNOWN"))
            except ValueError:
                state = CTalkState.UNKNOWN
            result[req_id] = CTalkStatusData(
                state=state,
                content=info.get("content", ""),
                msg=info.get("msg", ""),
                used_time=info.get("usedTime", 0),
            )
        return result


# ==================== 任务管理器 ====================


class PromptReverseManager:
    """提示词反求任务管理器（单例）

    职责：
    - 管理所有活跃的反求任务
    - 提交新任务（渲染图片 + 调用 API）
    - 根据轮询结果更新任务状态、触发回调
    - 提供待轮询任务列表给 Poller
    """

    _instance: Optional["PromptReverseManager"] = None
    _lock = Lock()

    def __init__(self, account: "Account"):
        self._api_client = CTalkApiClient(account)
        self._tasks: dict[str, PromptReverseTask] = {}
        self._tasks_lock = Lock()

    @classmethod
    def get_instance(cls, account: "Account" = None) -> "PromptReverseManager":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    if account is None:
                        raise RuntimeError("PromptReverseManager requires Account for first init")
                    cls._instance = cls(account)
        return cls._instance

    @classmethod
    def reset_instance(cls):
        with cls._lock:
            cls._instance = None

    def submit_task(
        self,
        image_path: str,
        on_success: Optional[Callable[[str], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
        prompt: str = "",
    ) -> Optional[str]:
        """提交提示词反求任务

        Args:
            image_path: 渲染图片的本地路径
            on_success: 成功回调，参数为反求得到的提示词内容
            on_error: 失败回调，参数为错误消息
            prompt: 自定义提示语（可选）

        Returns:
            任务的 req_id，失败返回 None
        """
        task = PromptReverseTask(callback=on_success, error_callback=on_error)

        try:
            image_base64 = self._encode_image(image_path)
        except Exception as e:
            logger.error(f"Failed to encode image: {e}")
            if on_error:
                on_error(f"图片编码失败: {e}")
            return None

        def _submit_job():
            try:
                log_id = self._api_client.submit(image_base64, task.req_id, prompt)
                logger.info(f"CTalk task submitted: req_id={task.req_id}, log_id={log_id}")
                task.state = CTalkState.RUNNING
                with self._tasks_lock:
                    self._tasks[task.req_id] = task
            except Exception as e:
                logger.error(f"CTalk submit failed: {e}")
                task.state = CTalkState.FAILED
                task.error_message = str(e)
                if task.error_callback:
                    task.error_callback(str(e))

        Thread(target=_submit_job, daemon=True).start()
        return task.req_id

    def get_pending_req_ids(self) -> list[str]:
        with self._tasks_lock:
            return [t.req_id for t in self._tasks.values() if t.is_waiting()]

    def update_from_poll_result(self, status_map: dict[str, CTalkStatusData]):
        with self._tasks_lock:
            for req_id, status in status_map.items():
                task = self._tasks.get(req_id)
                if task is None or task.is_done():
                    continue

                task.state = status.state

                if status.state == CTalkState.SUCCESS:
                    task.content = status.content
                    task.finished_at = time.time()
                    logger.info(f"CTalk task succeeded: {req_id}")
                    if task.callback:
                        task.callback(status.content)

                elif status.state == CTalkState.FAILED:
                    task.error_message = status.msg or "后端处理失败"
                    task.finished_at = time.time()
                    logger.warning(f"CTalk task failed: {req_id}, msg={status.msg}")
                    if task.error_callback:
                        task.error_callback(task.error_message)

    def cleanup_finished(self, max_age: float = 300.0):
        """清理已完成且超过 max_age 秒的任务"""
        now = time.time()
        with self._tasks_lock:
            expired = [
                rid for rid, t in self._tasks.items()
                if t.is_done() and now - t.finished_at > max_age
            ]
            for rid in expired:
                del self._tasks[rid]

    @staticmethod
    def _encode_image(image_path: str) -> str:
        data = Path(image_path).read_bytes()
        return base64.b64encode(data).decode("utf-8")


# ==================== 合批轮询器 ====================


class PromptReversePoller:
    """提示词反求合批轮询器

    所有视口共享一个轮询器实例，定时收集所有待查询的 req_id，
    合并为一次 API 调用，避免每个视口各自创建定时器。
    """

    def __init__(
        self,
        manager: PromptReverseManager,
        api_client: CTalkApiClient,
        interval: float = 5.0,
    ):
        self._manager = manager
        self._api_client = api_client
        self._interval = interval
        self._running = False
        self._thread: Optional[Thread] = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = Thread(
            target=self._polling_loop,
            daemon=True,
            name="PromptReversePoller",
        )
        self._thread.start()
        logger.info(f"PromptReversePoller started (interval: {self._interval}s)")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        logger.info("PromptReversePoller stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    def _polling_loop(self):
        while self._running:
            try:
                self._poll_once()
            except Exception as e:
                logger.error(f"PromptReversePoller error: {e}")

            for _ in range(int(self._interval * 4)):
                if not self._running:
                    break
                time.sleep(0.25)

    def _poll_once(self):
        req_ids = self._manager.get_pending_req_ids()
        if not req_ids:
            return

        logger.info(f"PromptReversePoller: querying {len(req_ids)} tasks")

        try:
            status_map = self._api_client.query_history(req_ids)
            self._manager.update_from_poll_result(status_map)
        except Exception as e:
            logger.error(f"PromptReversePoller: query failed: {e}")

        self._manager.cleanup_finished()
