from pathlib import Path
from uuid import uuid4

import bpy
from bpy_extras.io_utils import ImportHelper

from .studio import AIStudio
from ..i18n import OPS_TCTX


class AIStudioEntry(bpy.types.Operator):
    bl_idname = "bas.open_ai_studio"
    bl_description = "Open AI Studio"
    bl_translation_context = OPS_TCTX
    bl_label = "AI Studio Entry"

    def invoke(self, context, event):
        self.area = bpy.context.area
        self.app = AIStudio()
        self.app.draw_call_add(self.app.handler_draw)

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
            return {"FINISHED"}
        self.app.push_event(event)
        if self.app.should_pass_event():
            return {"PASS_THROUGH"}
        return {"RUNNING_MODAL"}


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

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        bpy.context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        img_path = Path(self.filepath).as_posix()
        FileCallbackRegistry.execute_callback(self.callback_id, img_path)
        return {"FINISHED"}


class EditImage(bpy.types.Operator):
    bl_idname = "bas.edit_image"
    bl_description = "Edit Image"
    bl_translation_context = OPS_TCTX
    bl_label = "Edit Image"

    @classmethod
    def poll(cls, context):
        space = context.space_data
        return getattr(space, "image", None)

    def execute(self, context):
        space = context.space_data
        origin = getattr(space, "image")
        origin.use_fake_user = True
        edit_image = origin.copy()

        edit_image.name = f"{origin.name}_edit"
        edit_image.use_fake_user = True
        aip = edit_image.blender_ai_studio_image_property
        aip.is_edit_image = True
        print(self.bl_idname, origin)

        space.image = edit_image
        space.ui_mode = "PAINT"
        bpy.ops.brush.asset_activate(
            asset_library_type='ESSENTIALS',
            asset_library_identifier="",
            relative_asset_identifier="brushes\\essentials_brushes-mesh_texture.blend\\Brush\\Erase Hard")
        return {"FINISHED"}


class ApplyEditImage(bpy.types.Operator):
    bl_idname = "bas.apply_edit_image"
    bl_description = "Apply Edit Image"
    bl_translation_context = OPS_TCTX
    bl_label = "Apply Edit Image"

    @classmethod
    def poll(cls, context):
        space = context.space_data
        image = getattr(space, "image", None)
        return image

    def execute(self, context):
        space = context.space_data
        origin = getattr(space, "image")
        print(self.bl_idname, origin)
        origin.use_fake_user = True
        origin.save()

        edit_image = origin.copy()
        edit_image.use_fake_user = True
        edit_image.name = f"{origin.name}_apply"
        aip = edit_image.blender_ai_studio_image_property
        aip.is_edit_image = False
        space.image = edit_image
        space.ui_mode = "VIEW"
        return {"FINISHED"}


class GenerateImage(bpy.types.Operator):
    bl_idname = "bas.generate_image"
    bl_description = "Generate Image"
    bl_translation_context = OPS_TCTX
    bl_label = "Generate Image"

    def execute(self, context):
        return {"FINISHED"}


def add_reference_image(context, image):
    ai = context.scene.blender_ai_studio_property
    ri = ai.reference_images.add()
    ri.image = image
    image.name = ri.name = f"{image.name}_REFERENCE"
    image.preview_ensure()


class SelectReferenceImageByFile(bpy.types.Operator, ImportHelper):
    bl_idname = "bas.select_reference_image_by_file"
    bl_label = "Select References By File"
    # File browser properties
    filename_ext = ""
    filter_glob: bpy.props.StringProperty(
        default="*.jpg;*.jpeg;*.png;*.bmp;*.tif;*.tiff;*.tga;*.exr;*.hdr",
        options={'HIDDEN'}
    )

    def execute(self, context):
        print(self.bl_idname, self.filepath)

        image = bpy.data.images.load(self.filepath)
        add_reference_image(context, image)
        return {"FINISHED"}


class SelectReferenceImageByImage(bpy.types.Operator):
    bl_idname = "bas.select_reference_image_by_image"
    bl_label = "Select References By Bl Image"
    icon_scale: bpy.props.FloatProperty(default=4, min=0.2, max=10, name="Icon Scale")

    def invoke(self, context, event):
        for i in bpy.data.images:
            if not i.preview:
                i.preview_ensure()
        wm = context.window_manager
        return wm.invoke_props_dialog(**{'operator': self, 'width': 300})

    def execute(self, context):
        image = getattr(context, "image", None)
        if image:
            print(self.bl_idname)
            add_reference_image(context, image)
            return {"FINISHED"}
        return {"CANCELLED"}

    def draw(self, context):
        ai = context.scene.blender_ai_studio_property
        layout = self.layout
        layout.prop(self, "icon_scale")
        for i in bpy.data.images:
            if i not in ai.all_references_images:
                if i.preview:
                    box = layout.box()
                    row = box.row()
                    row.operator_context = "EXEC_DEFAULT"
                    row.context_pointer_set("image", i)
                    row.template_icon(i.preview.icon_id, scale=self.icon_scale)
                    col = row.column(align=True)
                    col.operator(self.bl_idname, text=i.name, translate=False, emboss=False)
                    col.operator(self.bl_idname, icon="RESTRICT_SELECT_OFF",
                                 text=bpy.app.translations.pgettext_iface("Select Reference"),
                                 )
                else:
                    i.preview_ensure()


class RemoveReferenceImage(bpy.types.Operator):
    bl_idname = "bas.remove_reference_image"
    bl_label = "Remove References"

    index: bpy.props.IntProperty()

    def execute(self, context):
        ai = context.scene.blender_ai_studio_property
        ai.reference_images.remove(self.index)
        return {"FINISHED"}


clss = [
    AIStudioEntry,
    FileImporter,
    EditImage,
    ApplyEditImage,
    GenerateImage,

    RemoveReferenceImage,
    SelectReferenceImageByFile,
    SelectReferenceImageByImage,
]

reg, unreg = bpy.utils.register_classes_factory(clss)


def register():
    reg()


def unregister():
    unreg()
