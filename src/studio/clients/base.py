import json
import time
from typing import Self
from pathlib import Path
from ..account import Account
from ..tasks import TaskManager
from ..wrapper import BaseAdapter
from ...i18n import PROP_TCTX


class StudioHistoryItem:
    def __init__(self) -> None:
        self.result: dict = {}
        self.output_file: str = ""
        self.metadata: dict = {}
        self.vendor: str = ""
        self.index: int = 0
        self.timestamp: float = 0
        self.show_detail: bool = False

    def stringify(self) -> str:
        data = {
            "output_file": self.output_file,
            "metadata": self.metadata,
            "vendor": self.vendor,
            "index": self.index,
            "timestamp": self.timestamp,
        }
        return json.dumps(data)


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
        history_item = StudioHistoryItem()
        history_item.result = {}
        history_item.output_file = Path.home().joinpath("Desktop/OutputImage/AIStudio/Output.png").as_posix()
        history_item.metadata = {"prompt": "这是一个测试"}
        history_item.vendor = "NanoBananaPro"
        history_item.timestamp = time.time()
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


class StudioClient(BaseAdapter):
    VENDOR = ""
    _INSTANCE = None

    def __new__(cls, *args, **kwargs):
        if cls._INSTANCE is None:
            cls._INSTANCE = super().__new__(cls)
        return cls._INSTANCE

    def __init__(self) -> None:
        self._name = self.VENDOR
        self.help_url = ""
        self.task_manager = TaskManager.get_instance()
        self.task_id: str = ""
        self.is_task_submitting = False
        self.history = StudioHistory.get_instance()
        self.use_internal_prompt: bool = True
        self.error_messages: list = []

    @classmethod
    def get_instance(cls) -> Self:
        if cls._INSTANCE is None:
            cls._INSTANCE = cls()
        return cls._INSTANCE

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

    def draw_generation_panel(self):
        pass

    def draw_setting_panel(self):
        pass

    def draw_history_panel(self):
        pass

    def add_history(self, item: "StudioHistoryItem"):
        self.history.add(item)

    def calc_price(self, price_table: dict) -> int | None:
        return 999999

    def new_generate_task(self, account: "Account"):
        pass

    def cancel_generate_task(self):
        pass

    def query_task_elapsed_time(self) -> float:
        if not self.task_id:
            return 0
        if not (task := self.task_manager.get_task(self.task_id)):
            return 0
        return task.get_elapsed_time()

    def query_task_status(self) -> dict:
        if not self.task_id:
            return {}
        if not (task := self.task_manager.get_task(self.task_id)):
            return {}
        return task.get_info()

    def query_task_result(self):
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
