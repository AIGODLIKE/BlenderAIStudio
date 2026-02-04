import bpy
from threading import Thread
from .core import Account, AUTH_PATH
from .network import get_session, RETRY_STRATEGY, ADAPTER
from .websocket import WebSocketClient


__all__ = [
    # 核心
    "Account",
    "AUTH_PATH",
    # 网络
    "get_session",
    "RETRY_STRATEGY",
    "ADAPTER",
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


def register():
    """注册 Blender 插件时调用"""
    bpy.app.timers.register(init_account, first_interval=1, persistent=True)


def unregister():
    """注销 Blender 插件时调用"""
    if bpy.app.timers.is_registered(init_account):
        bpy.app.timers.unregister(init_account)
