import bpy
import json
import platform
import time
import traceback
from pathlib import Path
from threading import Thread
from typing import Optional, Self
from ..account import Account
from ..tasks import TaskManager, TaskState, Task, TaskResult
from ..wrapper import BaseAdapter
from ... import logger
from ...i18n import PROP_TCTX


class StudioHistoryItem:
    STATUS_PENDING = "pending"
    STATUS_PREPARING = "preparing"
    STATUS_RUNNING = "running"
    STATUS_PROCESSING = "processing"
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"
    STATUS_CANCELLED = "cancelled"

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
        self.task_manager: TaskManager = TaskManager.get_instance()

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

    def is_success(self) -> bool:
        return self.status == StudioHistoryItem.STATUS_SUCCESS or bool(self.outputs)

    def has_image(self) -> bool:
        return bool(self.get_output_file_image())

    def update_elapsed_time(self):
        if self.status not in (StudioHistoryItem.STATUS_RUNNING, StudioHistoryItem.STATUS_PROCESSING):
            return
        if not self.task_id:
            return
        task = self.task_manager.get_task(self.task_id)
        self.elapsed_time = task.get_elapsed_time() if task else self.elapsed_time

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
        history_item.task_id = ""
        self.add(history_item)

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


class StudioClient(BaseAdapter):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.task_manager = TaskManager.get_instance()
        self.task_id: str = ""
        self.is_task_submitting = False
        self.history = StudioHistory.get_instance()
        self.use_internal_prompt: bool = True
        self.error_messages: list = []

    def take_errors(self) -> list:
        errors = self.error_messages[:]
        self.error_messages.clear()
        return errors

    def push_error(self, error):
        self.error_messages.append(error)

    def get_ctxt(self) -> str:
        return PROP_TCTX

    def get_value(self, prop: str):
        return getattr(self, prop)

    def set_value(self, prop: str, value):
        setattr(self, prop, value)

    def get_properties(self) -> list[str]:
        return []

    def add_history(self, item: "StudioHistoryItem"):
        self.history.add(item)

    def remove_history(self, item: "StudioHistoryItem"):
        self.history.remove(item)

    def calc_price(self, price_table: dict) -> int | None:
        return 999999

    def add_task(self, account: "Account"):
        pass

    def _register_task_callbacks(self, task: Task):
        """注册标准回调（所有 Client 通用）"""
        task.register_callback("state_changed", self._on_task_state_changed)
        task.register_callback("progress_updated", self._on_progress)
        task.register_callback("cancelled", self._on_task_cancelled)
        task.register_callback("failed", self._on_task_failed)

    def _on_task_state_changed(self, event_data):
        """状态变化通用处理"""
        state = event_data["new_state"]
        task: Task = event_data["task"]
        item = self.history.find_by_task_id(task.task_id)
        if item:
            if state == TaskState.PREPARING:
                item.status = StudioHistoryItem.STATUS_PREPARING
                if not item.started_at:
                    item.started_at = time.time()
            elif state == TaskState.RUNNING or state == TaskState.PROCESSING:
                item.status = StudioHistoryItem.STATUS_RUNNING if state == TaskState.RUNNING else StudioHistoryItem.STATUS_PROCESSING
                if not item.started_at:
                    item.started_at = time.time()
            elif state == TaskState.COMPLETED:
                self.task_id = ""
        if state == TaskState.PREPARING:
            logger.info(f"⏳ 任务准备 {task.progress.message}")
        elif state == TaskState.RUNNING:
            logger.info(f"🚀 任务运行 {task.progress.message}")
        elif state == TaskState.COMPLETED:
            logger.info(f"✅ 任务完成: {task.task_id}")

    def _on_progress(self, event_data):
        task: Task = event_data["task"]
        progress: dict = event_data["progress"]
        item = self.history.find_by_task_id(task.task_id)
        if item:
            item.progress = progress["percentage"]
            item.progress_message = progress.get("message", "")
            item.elapsed_time = task.get_elapsed_time()
        logger.info(f"进度: {progress['percentage'] * 100}% - {progress.get('message', '')}")

    def _on_task_cancelled(self, event_data):
        task: Task = event_data["task"]
        if self.task_id == task.task_id:
            self.task_id = ""
        item = self.history.find_by_task_id(task.task_id)
        if item:
            item.status = StudioHistoryItem.STATUS_CANCELLED
            item.finished_at = time.time()
            self.history.update_item(item)
        logger.info(f"任务已取消: {task.task_id}")

    def _on_task_failed(self, event_data):
        task: Task = event_data["task"]
        result: TaskResult = event_data["result"]
        if not result.success:
            self.push_error(result.error_message)
            logger.error(result.error_message)
            logger.critical(f"任务失败: {task.task_id}")
        item = self.history.find_by_task_id(task.task_id)
        if item:
            item.status = StudioHistoryItem.STATUS_FAILED
            item.error_message = result.error_message or str(result.error or "")
            item.finished_at = time.time()
            self.history.update_item(item)
        Account.get_instance().fetch_credits()

    def cancel_generate_task(self):
        pass

    def query_task_elapsed_time(self) -> float:
        if not self.task_id:
            return 0
        if not (task := self.task_manager.get_task(self.task_id)):
            return 0
        return task.get_elapsed_time()

    def query_status(self) -> dict:
        if not self.task_id:
            return {}
        if not (task := self.task_manager.get_task(self.task_id)):
            return {}
        return task.get_info()

    def query_result(self):
        if not self.task_id:
            return None
        # 无任务
        if not (task := self.task_manager.get_task(self.task_id)):
            return None
        # 未完成
        if not task.is_finished():
            return
        # 无结果
        if not (result := task.result):
            return None
        # 执行失败
        if not result.is_success():
            error_msg = result.error_message
            print(f"任务失败: {error_msg}")
            return None
        image_data = result.get_data()
        print("任务完成！")
        return image_data
