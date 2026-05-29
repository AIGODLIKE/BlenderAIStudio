import traceback
from queue import Queue
from typing import Any

import bpy

from .logger import logger


class Timer:
    timer_queue = Queue()
    stoped = False

    @classmethod
    def put(cls, delegate: Any):
        if cls.stoped:
            return
        cls.timer_queue.put(delegate)

    @classmethod
    def executor(cls, t):
        if isinstance(t, (list, tuple)):
            t[0](*t[1:])
        else:
            t()

    @classmethod
    def stop_added(cls):
        cls.stoped = True

    @classmethod
    def start_added(cls):
        cls.stoped = False

    @classmethod
    def run(cls):
        return cls.run_ex(cls.timer_queue)

    @classmethod
    def run_ex(cls, queue: Queue):
        while not queue.empty():
            t = queue.get()
            try:
                cls.executor(t)
            except Exception as e:
                traceback.print_exc()
                logger.error("%s: %s", type(e).__name__, e)
            except KeyboardInterrupt:
                ...
        return 0.016666666666666666

    @classmethod
    def clear(cls):
        while not cls.timer_queue.empty():
            cls.timer_queue.get()

    @classmethod
    def wait_run(cls, func):
        def wrap(*args, **kwargs):
            q = Queue()

            def wrap_job(q):
                try:
                    res = func(*args, **kwargs)
                    q.put(res)
                except Exception as e:
                    q.put(e)

            cls.put((wrap_job, q))
            res = q.get()
            if isinstance(res, Exception):
                raise res
            return res

        return wrap

    @classmethod
    def reg(cls):
        bpy.app.timers.register(cls.run, persistent=True)

    @classmethod
    def unreg(cls):
        cls.clear()
        try:
            bpy.app.timers.unregister(cls.run)
        except Exception:
            ...


def privacy():
    from .preferences.privacy import collect_info, privacy_tips_popup
    collect_info()
    privacy_tips_popup()


def check_update():
    from .online_update_addon import OnlineUpdateAddon
    OnlineUpdateAddon.update_addon_version_info(True)  # 启动自检更新,如果有测提示更新


def check_failed_task():
    scene = bpy.context.scene
    if aii := getattr(scene, "blender_ai_studio_property", None):
        if t := aii.check_all_failed():
            return t
    return 1 / 2


def _force_account_mode():
    """启动时强制切换到 account 模式（兼容旧 preferences 中保存的 api 模式）"""
    from .utils import get_pref
    from .preferences import AuthMode
    pref = get_pref()
    if pref.account_auth_mode != AuthMode.ACCOUNT.value:
        pref.account_auth_mode = AuthMode.ACCOUNT.value


def register():
    Timer.reg()
    bpy.app.timers.register(privacy, first_interval=0.5)  # 只在第一次启动时执行
    bpy.app.timers.register(check_update, first_interval=1)  # 只在第一次启动时执行
    bpy.app.timers.register(check_failed_task, first_interval=0.1, persistent=True)
    bpy.app.timers.register(_force_account_mode, first_interval=0.1)


def unregister():
    Timer.unreg()
    if bpy.app.timers.is_registered(check_failed_task):
        bpy.app.timers.unregister(check_failed_task)
