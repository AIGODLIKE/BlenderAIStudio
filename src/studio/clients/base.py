import time
from .history import StudioHistory, StudioHistoryItem
from ..account import Account
from ..tasks import TaskManager, TaskState, Task, TaskResult
from ..wrapper import BaseAdapter
from ... import logger
from ...preferences import AuthMode
from ...i18n import PROP_TCTX


class StudioClient(BaseAdapter):
    _instance: dict = {}

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._instance[self] = self
        self.task_manager = TaskManager.get_instance()
        self.task_id: str = ""
        self.is_task_submitting = False
        self.history = StudioHistory.get_instance()
        self.use_internal_prompt: bool = True
        self.error_messages: list = []

    def __del__(self):
        self._instance.pop(self)

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

        item = self.history.find_by_task_id(task.task_id)
        if not item:
            return

        # 判断是否为网络异常 + 账号模式
        is_network_error = bool(result.error)

        account = Account.get_instance()
        is_account_mode = account.auth_mode == AuthMode.ACCOUNT.value

        if is_network_error and is_account_mode:
            # 网络异常且为账号模式，标记为待确认状态
            item.status = StudioHistoryItem.STATUS_UNKNOWN
            item.error_message = "Network error, syncing task status in background..."
            logger.warning(f"Task {task.task_id} network error, marked as unknown status")
        else:
            # 真正的失败
            item.status = StudioHistoryItem.STATUS_FAILED
            item.error_message = result.error_message or str(result.error or "")
            logger.error(result.error_message)
            logger.critical(f"Task failed: {task.task_id}")

        if not result.success:
            self.push_error(result.error or result.error_message)

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
