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


def register():
    Timer.reg()
    bpy.app.timers.register(privacy, first_interval=0.5)  # 只在第一次启动时执行
    bpy.app.timers.register(check_update, first_interval=1)  # 只在第一次启动时执行


def unregister():
    Timer.unreg()
