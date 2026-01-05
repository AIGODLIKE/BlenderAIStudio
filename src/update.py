from threading import Thread

import bpy


@bpy.app.handlers.persistent
def restore_history(a, b):
    """在加载新文件及打开blender的时候"""

    def load():
        from .studio.clients.base import StudioHistory
        StudioHistory.get_instance().restore_history()

    Thread(target=load, daemon=True).start()


# TODO 如果有多个场景?
def register():
    bpy.app.handlers.load_post.append(restore_history)


def unregister():
    if restore_history in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(restore_history)
