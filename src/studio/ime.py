import bpy

from ...External.input_method_hook import input_manager

# 自动处理输入法状态
@bpy.app.handlers.persistent
def on_load_pre(dummy):
    input_manager.refresh_input_method()


@bpy.app.handlers.persistent
def on_save_pre(dummy):
    input_manager.refresh_input_method()


def register():
    bpy.app.handlers.load_pre.append(on_load_pre)
    bpy.app.handlers.save_pre.append(on_save_pre)

    input_manager.refresh_input_method()


def unregister():
    if on_load_pre in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(on_load_pre)
    if on_save_pre in bpy.app.handlers.save_pre:
        bpy.app.handlers.save_pre.remove(on_save_pre)

    input_manager.cleanup()
