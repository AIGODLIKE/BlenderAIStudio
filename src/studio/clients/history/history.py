import bpy
import json
import platform
import time
import traceback
from pathlib import Path
from threading import Thread
from typing import Optional
from uuid import uuid4
from ...account import Account
from ...account.task_history import TaskHistoryData

from .... import logger


class StudioHistoryItem:
    STATUS_PENDING = "pending"
    STATUS_PREPARING = "preparing"
    STATUS_RUNNING = "running"
    STATUS_PROCESSING = "processing"
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"
    STATUS_CANCELLED = "cancelled"
    STATUS_UNKNOWN = "unknown"  # 网络异常，需要查询后端确认真实状态

    def __init__(self) -> None:
        self.result: dict = {}
        self.outputs: list[tuple[str, str]] = []
        self.metadata: dict = {}
        self.model: str = ""
        self.index: int = 0
        self.timestamp: float = 0
        self.show_detail: bool = False
        self.task_id: str = ""
        self.status: str = self.STATUS_PENDING
        self.progress: float = 0.0
        self.progress_message: str = ""
        self.elapsed_time: float = 0.0
        self.error_message: str = ""
        self.created_at: float = 0.0
        self.started_at: float = 0.0
        self.finished_at: float = 0.0

    def stringify(self) -> str:
        """序列化"""
        return json.dumps(self.data)

    @property
    def data(self) -> dict:
        """字典数据"""
        return {
            "outputs": self.outputs,
            "metadata": self.metadata,
            "model": self.model,
            "index": self.index,
            "timestamp": self.timestamp,
            "task_id": self.task_id,
            "status": self.status,
            "progress": self.progress,
            "progress_message": self.progress_message,
            "elapsed_time": self.elapsed_time,
            "error_message": self.error_message,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }

    @staticmethod
    def load(data: dict):
        history = StudioHistoryItem()
        history.load_old(data)
        for k in history.__dict__:
            if k not in data:
                continue
            setattr(history, k, data.get(k))
        return history

    # 旧版本历史记录兼容
    def load_old(self, data: dict):
        # 老版本只有图像数据
        if "vendor" not in data:
            return
        self.model = data.get("vendor", "")
        self.outputs = [("image/png", data.get("output_file", ""))]
        if "status" not in data and self.get_output_file_image():
            self.status = self.STATUS_SUCCESS
        else:
            self.status = self.STATUS_FAILED

    def is_pending(self) -> bool:
        return self.status == self.STATUS_PENDING

    def is_preparing(self) -> bool:
        return self.status == self.STATUS_PREPARING

    def is_running(self) -> bool:
        return self.status == self.STATUS_RUNNING

    def is_generating(self) -> bool:
        return self.status == self.STATUS_UNKNOWN

    def is_processing(self) -> bool:
        return self.status == self.STATUS_PROCESSING

    def is_success(self) -> bool:
        return self.status == self.STATUS_SUCCESS or bool(self.outputs)

    def is_failed(self) -> bool:
        return self.status == self.STATUS_FAILED

    def is_cancelled(self) -> bool:
        return self.status == self.STATUS_CANCELLED

    def is_finished(self) -> bool:
        return self.status in (self.STATUS_SUCCESS, self.STATUS_FAILED, self.STATUS_CANCELLED)

    def needs_status_sync(self) -> bool:
        return self.status == self.STATUS_UNKNOWN

    def has_image(self) -> bool:
        return bool(self.get_output_file_image())

    def need_update_elapsed_time(self) -> bool:
        return self.status not in (
            self.STATUS_SUCCESS,
            self.STATUS_FAILED,
            self.STATUS_CANCELLED,
        )

    def update_elapsed_time(self):
        if not self.need_update_elapsed_time():
            return
        if not self.task_id:
            return
        self.elapsed_time = time.time() - self.started_at

    def get_prompt(self):
        # 尝试从不同位置获取提示词
        prompt = self.metadata.get("prompt", "")  # 旧格式
        if not prompt and "params" in self.metadata:
            prompt = self.metadata["params"].get("prompt", "")  # 新格式
        return prompt

    def get_output_file_image(self):
        for output in self.outputs:
            if output[0].startswith("image/"):
                return output[1]
        return ""

    def get_one_output_file_by_mime_type(self, mime_type: str) -> str:
        for output in self.outputs:
            if output[0] == mime_type:
                return output[1]
        return ""

    def get_output_files_by_mime_type(self, mime_type: str) -> list[str]:
        return [output[1] for output in self.outputs if output[0] == mime_type]


class StudioHistory:
    _INSTANCE = None

    def __new__(cls, *args, **kwargs):
        if cls._INSTANCE is None:
            cls._INSTANCE = super().__new__(cls)
        return cls._INSTANCE

    def __init__(self):
        self.items: list[StudioHistoryItem] = []
        self.current_index = 0

    def add_fake_item(self):
        desktop = Path.home().joinpath("Desktop")
        output_file = desktop.joinpath("OutputImage/AIStudio/Output.png")
        if platform.system() == "Windows":
            output_file = desktop.joinpath("generated_images/generated_image.png")
        history_item = StudioHistoryItem()
        history_item.result = {}
        history_item.outputs = [("image/png", output_file.as_posix())]
        history_item.metadata = {"prompt": "这是一个测试"}
        history_item.model = "gemini-3-pro-image-preview"
        history_item.timestamp = time.time()
        history_item.started_at = time.time()
        history_item.task_id = str(uuid4())
        self.add(history_item)
        return history_item

    @classmethod
    def get_instance(cls) -> "StudioHistory":
        if cls._INSTANCE is None:
            cls._INSTANCE = cls()
        return cls._INSTANCE

    def add(self, item: "StudioHistoryItem"):
        self.current_index += 1
        item.index = self.current_index
        self.items.insert(0, item)
        self.save_history()

    def remove(self, item: "StudioHistoryItem"):
        try:
            self.items.remove(item)
            self.save_history()
        except ValueError:
            pass

    def find_by_task_id(self, task_id: str) -> Optional["StudioHistoryItem"]:
        for item in self.items:
            if item.task_id == task_id:
                return item
        return None

    def find_all_needs_status_sync_items(self) -> list[StudioHistoryItem]:
        return [item for item in self.items if item.needs_status_sync()]

    def load_from_task_history(self, task_history: "TaskHistoryData"):
        item = self.find_by_task_id(task_history.task_id)
        if not item:
            return
        if task_history.state.is_success():
            item.status = StudioHistoryItem.STATUS_SUCCESS
            item.finished_at = task_history.finished_at
            item.elapsed_time = item.finished_at - item.started_at
            item.progress = 100.0
            item.error_message = ""
            item.outputs = task_history.outputs
            item.result = task_history.result
        elif task_history.state.is_running():
            item.status = StudioHistoryItem.STATUS_UNKNOWN
            item.elapsed_time = time.time() - item.started_at
        elif task_history.state.is_failed():
            item.status = StudioHistoryItem.STATUS_FAILED
            item.finished_at = task_history.finished_at
            item.elapsed_time = item.finished_at - item.started_at
            item.progress = 0.0
            item.error_message = task_history.error_message
        elif task_history.state.is_unknown():
            item.status = StudioHistoryItem.STATUS_FAILED
            item.error_message = task_history.error_message
        if not task_history.state.is_running():
            self.save_history()

    def update_item(self, item: "StudioHistoryItem"):
        self.save_history()

    def save_history(self):
        """在添加的时候就保存到场景一下"""
        try:
            items = [item.data for item in self.items]
            stringify = json.dumps(items, ensure_ascii=True, indent=2)

            def save_task():
                bpy.context.scene.blender_ai_studio_property.generate_history = stringify

            bpy.app.timers.register(save_task, first_interval=0.1)
            logger.debug(f"save history {len(items)}")
            self.update_max_index()
        except Exception as e:
            logger.debug("保存历史记录失败", e.args)
            traceback.print_exc()

    def restore_history(self):
        try:
            data = json.loads(bpy.context.scene.blender_ai_studio_property.generate_history)
            if not isinstance(data, list):
                logger.debug("Invalid history data")
                logger.debug(data)
            items = [StudioHistoryItem.load(item) for item in data]
            logger.debug(f"load history {len(items)}")
            self.items = items
            self.update_max_index()
        except Exception as e:
            traceback.print_exc()
            logger.debug("恢复历史记录失败", e.args)

    def update_max_index(self):
        self.current_index = max([item.index for item in self.items] or [0])

    @classmethod
    def thread_restore_history(cls):
        """子线程恢复历史"""

        def load():
            cls.get_instance().restore_history()

        Thread(target=load, daemon=True).start()


def sync_history_timer():
    try:
        history = StudioHistory.get_instance()
        items = history.find_all_needs_status_sync_items()
        account = Account.get_instance()
        task_history_map = account.fetch_task_history([item.task_id for item in items])
        for task_history in task_history_map.values():
            history.load_from_task_history(task_history)
    except Exception as e:
        logger.error(f"Failed to sync history: {e}")
        traceback.print_exc()
    return 1
