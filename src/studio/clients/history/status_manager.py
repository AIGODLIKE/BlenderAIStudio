import bpy

from .status_sync import TaskStatusPoller, TaskStatusSyncService
from ..base import StudioHistory
from ...account import Account
from ....logger import logger
from ....utils import get_pref


class StatusManager:
    """任务状态管理器（单例）

    负责：
    - 启动/停止状态轮询器
    - 提供手动刷新接口（供 UI 使用）
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        self.poller = None
        self.sync_service = None

    @classmethod
    def get_instance(cls) -> "StatusManager":
        return cls()

    def ensure_sync_service(self):
        if self.sync_service:
            return
        account = Account.get_instance()
        history = StudioHistory.get_instance()
        self.sync_service = TaskStatusSyncService(account, history)

    def start(self, interval: float = 10.0):
        if self.poller and self.poller.running:
            logger.warning("Task status poller is already running")
            return

        self.ensure_sync_service()
        self.poller = TaskStatusPoller(self.sync_service, interval)
        self.poller.start()

        logger.info("Task status manager started")

    def stop(self):
        if self.poller:
            self.poller.stop()
            self.poller = None

        self.sync_service = None
        logger.info("Task status manager stopped")

    def refresh_task(self, task_id: str) -> bool:
        self.ensure_sync_service()

        try:
            return self.sync_service.sync_single_task(task_id)
        except Exception as e:
            logger.error(f"Failed to refresh task {task_id}: {e}")
            return False

    def refresh_all_unknown_tasks(self) -> int:
        self.ensure_sync_service()

        # 找出所有待同步的任务
        history = StudioHistory.get_instance()
        items_to_sync = history.find_all_needs_status_sync_items()

        if not items_to_sync:
            logger.info("No tasks to refresh")
            return 0

        task_ids = [item.task_id for item in items_to_sync]
        return self.sync_service.sync_tasks(task_ids)


def start():
    if not get_pref():
        return 1
    # 启动任务状态轮询器
    try:
        status_manager = StatusManager.get_instance()
        status_manager.start(interval=10.0)  # 每 10 秒轮询一次
        logger.info("Task status poller started")
    except Exception as e:
        logger.error(f"Failed to start task status poller: {e}")


def stop():
    try:
        status_manager = StatusManager.get_instance()
        status_manager.stop()
        logger.info("Task status poller stopped")
    except Exception as e:
        logger.error(f"Failed to stop task status poller: {e}")


def register():
    bpy.app.timers.register(start, first_interval=1)


def unregister():
    stop()
