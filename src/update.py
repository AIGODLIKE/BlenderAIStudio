import bpy


@bpy.app.handlers.persistent
def load_post(a, b):
    """在加载新文件及打开blender的时候"""
    from .studio.clients.base import StudioHistory
    StudioHistory.thread_restore_history()


# TODO 如果有多个场景?
def register():
    bpy.app.handlers.load_post.append(load_post)


def unregister():
    if load_post in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(load_post)
