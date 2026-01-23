from threading import Thread
import bpy
import random

def register():
    def install():
        from ...utils import PkgInstaller
        PkgInstaller.try_install("slimgui")
        # TODO 多开bug
        # def r(): #修了这个会有另一外bug出现
        # bpy.app.timers.register(r, first_interval=round(random.uniform(1.0, 10.0), 2)) # 需要随机延迟，不然会导致多开的时候闪退
    Thread(target=install, daemon=True).start()


def unregister():
    pass
