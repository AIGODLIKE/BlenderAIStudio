import json
import platform
import time
from pathlib import Path
from typing import Self

import bpy

from ..tasks import TaskManager
from ..wrapper import BaseAdapter
from ... import logger
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
        """序列化"""
        return json.dumps(self.data)

    @property
    def data(self) -> dict:
        """字典数据"""
        return {
            "output_file": self.output_file,
            "metadata": self.metadata,
            "vendor": self.vendor,
            "index": self.index,
            "timestamp": self.timestamp,
        }

    @staticmethod
    def load(data: dict):
        history = StudioHistoryItem()
        for k in (
                "output_file",
                "metadata",
                "vendor",
                "index",
                "timestamp",
        ):
            if k in data:
                setattr(history, k, data[k])
        return history


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
        history_item.output_file = output_file.as_posix()
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
        self.save_history()

    def remove(self, item: "StudioHistoryItem"):
        try:
            self.items.remove(item)
            self.save_history()
        except ValueError:
            pass

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
            import traceback
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
            import traceback
            traceback.print_exc()
            logger.debug("恢复历史记录失败", e.args)

    def update_max_index(self):
        self.current_index = max([item.index for item in self.items] or [-1]) + 1

    @classmethod
    def thread_restore_history(cls):
        """子线程恢复历史"""
        from threading import Thread
        def load():
            cls.get_instance().restore_history()

        Thread(target=load, daemon=True).start()


class StudioClient(BaseAdapter):
    from ..account import Account
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

    def add_history(self, item: "StudioHistoryItem"):
        self.history.add(item)

    def remove_history(self, item: "StudioHistoryItem"):
        self.history.remove(item)

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
