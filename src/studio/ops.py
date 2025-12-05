from pathlib import Path
from uuid import uuid4

import bpy
from bpy_extras.io_utils import ImportHelper

from .studio import AIStudio
from ..i18n import OPS_TCTX
from ..utils import get_text_generic_keymap, get_text_window, get_pref


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


class DrawImageMask(bpy.types.Operator):
    bl_idname = "bas.draw_mask"
    bl_label = "Draw Mask"
    bl_options = {"REGISTER"}
    bl_translation_context = OPS_TCTX

    @classmethod
    def poll(cls, context):
        space = context.space_data
        image = getattr(space, "image", None)
        return image and not image.blender_ai_studio_property.is_mask_image

    def execute(self, context):
        bpy.ops.ed.undo_push(message="Push Undo")
        from bl_ui.properties_paint_common import UnifiedPaintPanel
        space = context.space_data
        print(self.bl_idname)

        image = getattr(space, "image")
        image.use_fake_user = True
        scene_prop = context.scene.blender_ai_studio_property

        name = f"{image.name}_mask"

        mask_image = image.copy()
        mask_image.use_fake_user = True
        mask_image.pack()
        # mask_image.preview_ensure()
        mask_image.filepath = ""
        mask_image.name = name

        mi = scene_prop.mask_images.add()  # 新创建一个mask图
        mi.name = name
        mi.image = mask_image

        aip = mask_image.blender_ai_studio_property
        aip.is_mask_image = True
        aip.origin_image = image

        space.image = mask_image
        space.ui_mode = "PAINT"
        bpy.ops.brush.asset_activate(
            "EXEC_DEFAULT",
            False,
            asset_library_type='ESSENTIALS',
            asset_library_identifier="",
            relative_asset_identifier="brushes\\essentials_brushes-mesh_texture.blend\\Brush\\Paint Hard Pressure")
        paint_settings = UnifiedPaintPanel.paint_settings(context).unified_paint_settings
        paint_settings.size = 4
        paint_settings.color = [1, 0, 0]
        if space.ui_mode == "PAINT":
            space.uv_editor.show_uv = False
        bpy.ops.ed.undo_push(message="Push Undo")
        return {"FINISHED"}


class ApplyImageMask(bpy.types.Operator):
    bl_idname = "bas.apply_image_mask"
    bl_translation_context = OPS_TCTX
    bl_label = "Apply Image Mask"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        space = context.space_data
        image = getattr(space, "image", None)
        return image and image.blender_ai_studio_property.origin_image

    def execute(self, context):
        space = context.space_data
        image = getattr(space, "image")
        print(self.bl_idname, image)
        bpy.ops.image.save("EXEC_DEFAULT", False)
        image.preview_ensure()
        image.use_fake_user = True
        if image.preview:
            image.preview.reload()
        # image.pack()
        # image.filepath = ""

        ai = image.blender_ai_studio_property
        oii = context.scene.blender_ai_studio_property

        space.image = ai.origin_image
        space.ui_mode = "VIEW"
        for index, m in enumerate(oii.mask_images):
            if m.image == image:
                oii.mask_index = index
                continue
        return {"FINISHED"}


class SelectMask(bpy.types.Operator):
    bl_idname = "bas.select_mask"
    bl_translation_context = OPS_TCTX
    bl_label = "Select Mask"
    bl_options = {"REGISTER"}
    index: bpy.props.IntProperty()
    remove: bpy.props.BoolProperty(default=False)

    @classmethod
    def description(cls, context, properties):
        if properties.index == -1:
            return "Not using mask"
        return cls.bl_label

    @classmethod
    def poll(cls, context):
        space = context.space_data
        image = getattr(space, "image", None)
        return image

    def invoke(self, context, event):
        return context.window_manager.invoke_popup(self)

    def execute(self, context):
        space = context.space_data
        image = getattr(space, "image", None)
        oii = context.scene.blender_ai_studio_property
        print(self.bl_idname, self.index, image)

        if self.remove:
            oii.mask_images.remove(self.index)
        else:
            oii.mask_index = self.index
            if space.ui_mode == "PAINT":
                space.image = oii.active_mask
        return {"FINISHED"}

    def draw(self, context):
        layout = self.layout
        self.draw_select_mask(context, layout)

    @staticmethod
    def draw_select_mask(context, layout, use_box=False):
        column = layout.column(align=True)
        column.operator_context = "EXEC_DEFAULT"
        # column.label(text=SelectMask.bl_label)
        oii = context.scene.blender_ai_studio_property
        for index, m in enumerate(oii.mask_images):
            if m.image and m.image.preview:
                box = column.box() if use_box else column.column(align=True)
                box.template_icon(m.image.preview.icon_id, scale=6)
                row = box.row(align=True)
                ops = row.operator("bas.select_mask", text=m.image.name, icon="RESTRICT_SELECT_OFF", translate=False)
                ops.index = index
                ops.remove = False
                ops = row.operator("bas.select_mask", text="", icon="TRASH")
                ops.index = index
                ops.remove = True
        if len(oii.mask_images) == 0:
            column.label(text="No mask available, please draw")


def add_reference_image(context, image, image_name=False):
    ai = context.scene.blender_ai_studio_property
    ri = ai.reference_images.add()
    ri.image = image
    ri.name = f"{image.name}_REFERENCE"
    if image_name:
        image.name = ri.name
    image.preview_ensure()


class SelectReferenceImageByFile(bpy.types.Operator, ImportHelper):
    bl_idname = "bas.select_reference_image_by_file"
    bl_label = "Select References By File"
    bl_translation_context = OPS_TCTX
    bl_options = {"REGISTER"}

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
    bl_translation_context = OPS_TCTX
    bl_options = {"REGISTER"}

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
            if i not in ai.all_references_images and not i.blender_ai_studio_property.is_mask_image:
                if i.preview:
                    box = layout.box()
                    row = box.row()
                    row.operator_context = "EXEC_DEFAULT"
                    row.context_pointer_set("image", i)
                    row.template_icon(i.preview.icon_id, scale=self.icon_scale)
                    col = row.column()
                    col.operator(self.bl_idname, text=i.name, translate=False, emboss=False)
                    col.operator(self.bl_idname, icon="RESTRICT_SELECT_OFF",
                                 text=bpy.app.translations.pgettext_iface("Select Reference"),
                                 )
                else:
                    i.preview_ensure()


class ReplaceReferenceImage(bpy.types.Operator):
    bl_idname = "bas.replace_reference_image"
    bl_label = "Replace References"
    bl_translation_context = OPS_TCTX
    bl_options = {"REGISTER"}

    icon_scale: bpy.props.FloatProperty(default=4, min=0.2, max=10, name="Icon Scale")
    index: bpy.props.IntProperty()

    def invoke(self, context, event):
        for i in bpy.data.images:
            if not i.preview:
                i.preview_ensure()
        wm = context.window_manager
        return wm.invoke_props_dialog(**{'operator': self, 'width': 300})

    def execute(self, context):
        image = getattr(context, "image", None)
        if image:
            oii = context.scene.blender_ai_studio_property
            oii.reference_images[self.index].image = image
            print(self.bl_idname, image, self.index)
            return {"FINISHED"}
        return {"CANCELLED"}

    def draw(self, context):
        ai = context.scene.blender_ai_studio_property
        layout = self.layout
        layout.prop(self, "icon_scale")
        for i in bpy.data.images:
            if i not in ai.all_references_images and not i.blender_ai_studio_property.is_mask_image:
                if i.preview:
                    box = layout.box()
                    row = box.row()
                    row.operator_context = "EXEC_DEFAULT"
                    row.context_pointer_set("image", i)
                    row.template_icon(i.preview.icon_id, scale=self.icon_scale)
                    col = row.column()
                    col.operator(self.bl_idname, text=i.name, translate=False, emboss=False).index = self.index
                    col.operator(self.bl_idname, icon="RESTRICT_SELECT_OFF",
                                 text=bpy.app.translations.pgettext_iface("Replace References"),
                                 ).index = self.index
                else:
                    i.preview_ensure()


class RemoveReferenceImage(bpy.types.Operator):
    bl_idname = "bas.remove_reference_image"
    bl_label = "Remove References"
    bl_options = {"REGISTER"}

    index: bpy.props.IntProperty()

    def execute(self, context):
        ai = context.scene.blender_ai_studio_property
        ai.reference_images.remove(self.index)
        return {"FINISHED"}


class GenerateImage(bpy.types.Operator):
    bl_idname = "bas.generate_image"
    bl_description = "Generate Image"
    bl_translation_context = OPS_TCTX
    bl_label = "Generate Image"
    bl_options = {"REGISTER"}

    def execute(self, context):
        print(self.bl_idname)
        return {"FINISHED"}


class ReRenderImage(bpy.types.Operator):
    bl_idname = "bas.rerender_image"
    bl_description = "ReRender Image"
    bl_translation_context = OPS_TCTX
    bl_label = "ReRender Image"
    bl_options = {"REGISTER"}

    def execute(self, context):
        print(self.bl_idname)
        return {"FINISHED"}


class FinalizeCompositeImage(bpy.types.Operator):
    bl_idname = "bas.finalize_composite"
    bl_description = "Finalize Composite"
    bl_translation_context = OPS_TCTX
    bl_label = "Finalize Composite"
    bl_options = {"REGISTER"}

    def execute(self, context):
        print(self.bl_idname)
        return {"FINISHED"}


def get_text_data(context) -> bpy.types.Text:
    """
    获取脚本数据块

    :param context:
    :return:
    """
    prompt = context.scene.blender_ai_studio_property.prompt

    name = "Prompt"
    text = bpy.data.texts.get(name)
    if text is None:
        text = bpy.data.texts.new(name)
    text.clear()
    text.write(prompt)
    text.blender_ai_studio_prompt_hash = str(hash(prompt))
    return text


class PromptEdit(bpy.types.Operator):
    bl_idname = 'bas.prompt_edit'
    bl_label = 'Prompt Edit'

    @staticmethod
    def add_save_key(context):
        keymap = get_text_generic_keymap(context)
        if keymap is not None:
            keymap.keymap_items.new(PromptSave.bl_idname, type="S", value="PRESS", ctrl=True)

    def execute(self, context):
        get_text_window(context, get_text_data(context))
        self.add_save_key(context)
        return {'FINISHED'}


def draw_save_script_button(self, context):
    layout = self.layout

    text = context.space_data.text
    prompt = context.scene.blender_ai_studio_property.prompt

    # layout.prop(text, "blender_ai_studio_prompt_hash")
    # layout.label(text=str(hash(prompt)))
    if getattr(text, "blender_ai_studio_prompt_hash", False) == str(hash(prompt)):
        row = layout.row()
        row.alert = True
        text = bpy.app.translations.pgettext("Save Prompt Ctrl + S")
        row.operator(PromptSave.bl_idname, text=text)


class PromptSave(bpy.types.Operator):
    bl_label = 'Save script'
    bl_idname = 'bas.prompt_save'

    @classmethod
    def poll(cls, context):
        pref = get_pref()
        prompt = context.scene.blender_ai_studio_property.prompt
        h = context.space_data.text.blender_ai_studio_prompt_hash
        hash_ok = h == str(hash(prompt))
        return hash_ok

    @staticmethod
    def register_ui():
        bpy.types.TEXT_HT_header.append(draw_save_script_button)

    @staticmethod
    def unregister_ui():
        bpy.types.TEXT_HT_header.remove(draw_save_script_button)

    def remove_save_key(self, context):
        keymap = get_text_generic_keymap(context)
        if keymap is not None:
            while True:
                ops = keymap.keymap_items.find_from_operator(self.bl_idname)
                if ops is None:
                    break
                keymap.keymap_items.remove(ops)

    def execute(self, context):
        text = context.space_data.text
        context.scene.blender_ai_studio_property.prompt = text.as_string()
        bpy.data.texts.remove(text)
        self.remove_save_key(context)
        bpy.ops.wm.window_close()
        return {'FINISHED'}


clss = [
    AIStudioEntry,
    FileImporter,

    SelectMask,
    DrawImageMask,
    ApplyImageMask,

    RemoveReferenceImage,
    SelectReferenceImageByFile,
    SelectReferenceImageByImage,
    ReplaceReferenceImage,

    GenerateImage,
    ReRenderImage,
    FinalizeCompositeImage,

    PromptEdit,
    PromptSave,
]

reg, unreg = bpy.utils.register_classes_factory(clss)


def register():
    reg()
    PromptSave.register_ui()


def unregister():
    unreg()
    PromptSave.unregister_ui()
