from pathlib import Path
from uuid import uuid4

import bpy
from bpy_extras.io_utils import ImportHelper, ExportHelper

from ..i18n import OPS_TCTX


class AIStudioEntry(bpy.types.Operator):
    bl_idname = "bas.open_ai_studio"
    bl_description = "Open AI Studio"
    bl_translation_context = OPS_TCTX
    bl_label = "AI Studio Entry"
    entry_pool: dict = {}

    def invoke(self, context, event):
        from .studio import AIStudio

        self.area = bpy.context.area
        if self.area.as_pointer() in self.entry_pool:
            # self.report({"ERROR"}, "AI Studio is already opened")
            app = self.entry_pool[self.area.as_pointer()]
            app.shutdown()
            return {"FINISHED"}
        self.app = AIStudio()
        self.app.draw_call_add(self.app.handler_draw)
        self.entry_pool[self.area.as_pointer()] = self.app

        self._timer = context.window_manager.event_timer_add(1 / 60, window=context.window)
        context.window_manager.modal_handler_add(self)

        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if context.area:
            if context.area != self.area:
                return {"PASS_THROUGH"}
            context.area.tag_redraw()
        else:
            self.app.queue_shoutdown()
        if self.app.should_exit():
            self.app.shutdown()
        if self.app.is_closed():
            print("AI Studio closed")
            self.entry_pool.pop(self.area.as_pointer(), None)
            return {"FINISHED"}
        self.app.push_event(event)
        if self.app.should_pass_event():
            return {"PASS_THROUGH"}
        return {"RUNNING_MODAL"}

    @classmethod
    def close_all(cls):
        """关闭所有的窗口
        避免出现在显示窗口时关闭插件bug
        """
        for app in cls.entry_pool.values():
            app.shutdown()


class FileCallbackRegistry:
    """管理文件选择回调的注册表"""

    _registry = {}

    @classmethod
    def register_callback(cls, callback, *args, **kwargs):
        """注册回调并返回唯一ID"""
        callback_id = str(uuid4())
        cls._registry[callback_id] = {"callback": callback, "args": args, "kwargs": kwargs}
        return callback_id

    @classmethod
    def execute_callback(cls, callback_id, filepath):
        """执行注册的回调"""
        if callback_id in cls._registry:
            data = cls._registry.pop(callback_id)  # 执行后移除
            callback = data["callback"]
            args = data["args"]
            kwargs = data["kwargs"]
            return callback(filepath, *args, **kwargs)
        return None


class FileImporter(bpy.types.Operator, ImportHelper):
    bl_idname = "bas.file_importer"
    bl_label = "Import File"

    filter_glob: bpy.props.StringProperty(default="*.png;*.jpg;*.jpeg;*.bmp;*.tiff;", options={"HIDDEN"})
    filepath: bpy.props.StringProperty(subtype="FILE_PATH")
    callback_id: bpy.props.StringProperty()

    # 定义一个用于多文件选择的集合属性
    files: bpy.props.CollectionProperty(
        type=bpy.types.OperatorFileListElement,
        options={'HIDDEN', 'SKIP_SAVE'}
    )
    # 用于存放所选文件夹路径的属性
    directory: bpy.props.StringProperty(
        subtype='DIR_PATH',
        options={'HIDDEN', 'SKIP_SAVE'}
    )

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        bpy.context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        images = []
        for file in self.files:
            img_path = Path(self.directory).joinpath(file.name).as_posix()
            images.append(img_path)
        FileCallbackRegistry.execute_callback(self.callback_id, images)
        return {"FINISHED"}


class FileExporter(bpy.types.Operator, ExportHelper):
    bl_idname = "bas.file_exporter"
    bl_label = "Export File"

    filename_ext = ".png"

    filter_glob: bpy.props.StringProperty(default="*.png;*.jpg;*.jpeg;", options={"HIDDEN"})
    filepath: bpy.props.StringProperty(subtype="FILE_PATH")
    callback_id: bpy.props.StringProperty()

    def execute(self, context):
        img_path = Path(self.filepath).as_posix()
        FileCallbackRegistry.execute_callback(self.callback_id, img_path)
        return {"FINISHED"}


clss = [
    AIStudioEntry,
    FileImporter,
    FileExporter,
]

reg, unreg = bpy.utils.register_classes_factory(clss)


def register():
    reg()


def unregister():
    AIStudioEntry.close_all()
    unreg()
