import time
from pathlib import Path

import bpy
from bpy_extras.io_utils import ImportHelper

from .. import logger
from ..i18n.translations.zh_HANS import OPS_TCTX
from ..utils import png_name_suffix, refresh_image_preview, get_temp_folder


def add_reference_image(context, image, image_name=False):
    ai = context.scene.blender_ai_studio_property
    ri = ai.reference_images.add()
    ri.image = image
    ri.name = png_name_suffix(image.name, "_reference")
    if image_name:
        image.name = ri.name
    refresh_image_preview(image)


class SelectReferenceImageByFile(bpy.types.Operator, ImportHelper):
    bl_idname = "bas.select_reference_image_by_file"
    bl_label = "Select Reference By File"
    bl_translation_context = OPS_TCTX
    bl_options = {"REGISTER"}

    # File browser properties
    filename_ext = ""
    filter_glob: bpy.props.StringProperty(
        default="*.jpg;*.jpeg;*.png;*.bmp;*.tif;*.tiff;*.tga;*.exr;*.hdr",
        options={"HIDDEN"},
    )

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

    def execute(self, context):
        for file in self.files:
            img_path = Path(self.directory).joinpath(file.name).as_posix()
            image = bpy.data.images.load(img_path)
            add_reference_image(context, image)
        return {"FINISHED"}


class SelectReferenceImageByImage(bpy.types.Operator):
    bl_idname = "bas.select_reference_image_by_image"
    bl_label = "Select Reference By Bl Image"
    bl_translation_context = OPS_TCTX
    bl_options = {"REGISTER"}

    icon_scale: bpy.props.FloatProperty(default=4, min=0.2, max=10, name="Icon Scale")

    def invoke(self, context, event):
        for i in bpy.data.images:
            if not i.preview:
                i.preview_ensure()
        wm = context.window_manager
        return wm.invoke_props_dialog(**{"operator": self, "width": 300})

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
        count = 0
        for i in bpy.data.images:
            if i not in ai.all_references_images and not i.blender_ai_studio_property.is_mask_image:
                if i.preview:
                    box = layout.box()
                    row = box.row()
                    row.operator_context = "EXEC_DEFAULT"
                    row.context_pointer_set("image", i)
                    row.template_icon(i.preview.icon_id, scale=self.icon_scale)
                    col = row.column()
                    col.operator(self.bl_idname, text=i.name, translate=False, emboss=False, icon="RESTRICT_SELECT_OFF")
                    count += 1
                else:
                    i.preview_ensure()
        if count == 0:
            layout.label(text="No images")


class ReplaceReferenceImage(bpy.types.Operator):
    bl_idname = "bas.replace_reference_image"
    bl_label = "Replace Reference Image"
    bl_translation_context = OPS_TCTX
    bl_options = {"REGISTER"}

    icon_scale: bpy.props.FloatProperty(default=4, min=0.2, max=10, name="Icon Scale")
    index: bpy.props.IntProperty()

    def invoke(self, context, event):
        for i in bpy.data.images:
            if not i.preview:
                i.preview_ensure()
        wm = context.window_manager
        return wm.invoke_props_dialog(**{"operator": self, "width": 300})

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
                    col.operator(
                        self.bl_idname,
                        icon="RESTRICT_SELECT_OFF",
                    ).index = self.index
                else:
                    i.preview_ensure()


class RemoveReferenceImage(bpy.types.Operator):
    bl_idname = "bas.remove_reference_image"
    bl_label = "Remove Reference Image"
    bl_options = {"REGISTER"}

    index: bpy.props.IntProperty()

    def execute(self, context):
        ai = context.scene.blender_ai_studio_property
        ai.reference_images.remove(self.index)
        return {"FINISHED"}


class ClipboardPasteReferenceImage(bpy.types.Operator):
    bl_idname = "bas.clipboard_paste_reference_image"
    bl_label = "Paste Reference Image"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        is_image_editor = context.area and context.area.type == "IMAGE_EDITOR"
        # try:
        #     return bpy.ops.image.clipboard_paste.poll() and is_image_editor
        # except Exception:
        return is_image_editor

    def execute(self, context):
        # 直接新建窗口并设为 Image Editor
        if not context.space_data:
            return {"CANCELLED"}

        old_image = context.space_data.image
        region = context.region

        if not region:
            logger.warning("Paste image: no valid Image Editor region")
            return {"FINISHED"}
        try:
            with bpy.context.temp_override():
                result = bpy.ops.image.clipboard_paste()
            if result != {"FINISHED"}:
                logger.warning("Paste image failed: %s", result)
                return {"FINISHED"}
        except Exception as e:
            logger.error(e)
            return {"FINISHED"}
        new_image = context.space_data.image
        if new_image != old_image:
            try:
                image_save_path = get_temp_folder(prefix="paste_image")
            except PermissionError as e:
                self.report({"ERROR"}, str(e))
                return {"CANCELLED"}
            image_name = f"paste_image_{time.time()}.png"
            image_path = Path(image_save_path).joinpath(image_name).as_posix()

            new_image.save(filepath=image_path)
            context.space_data.image = old_image
            add_reference_image(context, new_image)
        return {"FINISHED"}
