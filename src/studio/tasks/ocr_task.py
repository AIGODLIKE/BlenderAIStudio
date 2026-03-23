from pathlib import Path
from typing import TYPE_CHECKING
from typing_extensions import override

from .task import Task, TaskResult
from ..account.network import get_session
from ...logger import logger

if TYPE_CHECKING:
    from ..account import Account


class OCRTask(Task):
    """OCR任务

    使用 API 进行图像 OCR。
    """

    def __init__(self, image_path: str, account: "Account"):
        self.image_path: str = image_path
        self.account: "Account" = account
        super().__init__("OCR")

    @override
    def prepare(self) -> tuple[bool, Exception | None]:
        """准备任务"""
        if not Path(self.image_path).exists():
            return False, FileNotFoundError(f"Image file not found: {self.image_path}")

        if not self.account.token:
            return False, PermissionError("Not logged in")

        self.update_progress(1, "提交任务...")
        return True, None

    @override
    def execute(self) -> TaskResult:
        """执行任务

        1. 调用 API 提交图片
        2. 轮询等待结果
        3. 返回结果图片数据
        """
        # 提交任务
        task_type = "2"

        url = f"{self.account.service_url}/service/zt-api"
        headers = {
            "X-Auth-T": self.account.token,
            "X-REQ-ID": self.task_id,
            "X-TASK-TYPE": task_type,
        }

        try:
            with open(self.image_path, "rb") as f:
                files = {"file": (Path(self.image_path).name, f, "image/png")}
                session = get_session()
                _ = session.post(url, headers=headers, files=files, timeout=30)

            self.update_progress(2, "任务已提交, 等待处理...")

            # 异步任务, 所以这里直接返回异常
            e = Exception("OCR is submitted, please wait for the result")
            return TaskResult.failure_result(e, str(e))

        except Exception as e:
            logger.error(f"OCR: 请求失败 - {e}")
            return TaskResult.failure_result(e, str(e))

    @override
    def cleanup(self) -> None:
        """清理资源"""
        pass
