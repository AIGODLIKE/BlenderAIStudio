import bpy
from threading import Thread

from .core import Account, AUTH_PATH
from .network import get_session, RETRY_STRATEGY, ADAPTER
from .task_history import (
    TaskStatus,
    TaskStatusData,
    TaskHistoryData,
    AccountTaskHistory,
)
from .task_sync import (
    StatusResponseParser,
    TaskSyncService,
    TaskStatusPoller,
)
from .websocket import WebSocketClient
from ...logger import logger
from ...utils import get_pref


__all__ = [
    # 核心
    "Account",
    "AUTH_PATH",
    # 网络
    "get_session",
    "RETRY_STRATEGY",
    "ADAPTER",
    # 任务历史
    "TaskStatus",
    "TaskStatusData",
    "TaskHistoryData",
    "AccountTaskHistory",
    # 任务同步
    "StatusResponseParser",
    "TaskSyncService",
    "TaskStatusPoller",
    # WebSocket
    "WebSocketClient",
    # 注册函数
    "init_account",
    "start_task_status_poller",
    "stop_task_status_poller",
    "register",
    "unregister",
]


# ==================== Blender 集成函数 ====================


def init_account():
    def init():
        account = Account.get_instance()
        account.init()

    Thread(target=init, daemon=True).start()
    return 1


def start_task_status_poller():
    if not get_pref():
        return 1

    try:
        account = Account.get_instance()
        account.task_poller.start()
    except Exception as e:
        logger.error(f"Failed to start task status poller: {e}")


def stop_task_status_poller():
    try:
        account = Account.get_instance()
        account.task_poller.stop()
        logger.info("Task status poller stopped")
    except Exception as e:
        logger.error(f"Failed to stop task status poller: {e}")


def register():
    bpy.app.timers.register(init_account, first_interval=1, persistent=True)
    bpy.app.timers.register(start_task_status_poller, first_interval=1, persistent=True)


def unregister():
    if bpy.app.timers.is_registered(init_account):
        bpy.app.timers.unregister(init_account)
    stop_task_status_poller()
