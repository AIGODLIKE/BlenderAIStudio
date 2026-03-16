import bpy

from ..i18n.translations.zh_HANS import OPS_TCTX
from ..utils import png_name_suffix, refresh_image_preview, get_edit_main_image


class PublicPoll:
    bl_options = {"REGISTER"}
    bl_translation_context = OPS_TCTX

    @classmethod
    def poll(cls, context):
        space = context.space_data
        image = getattr(space, "image", None)
        return image


class SwitchPaint:
    run_count = 0

    def start_switch(self, context):
        space = context.space_data
        space.ui_mode = "PAINT"
        context.window_manager.modal_handler_add(self)  # 进入modal为了切换笔刷及画笔颜色
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        from bl_ui.properties_paint_common import UnifiedPaintPanel

        space = context.space_data
        if space.ui_mode == "PAINT":
            space.uv_editor.show_uv = False
        if paint_settings := getattr(UnifiedPaintPanel.paint_settings(context), "unified_paint_settings", None):
            bpy.ops.brush.asset_activate(
                "EXEC_DEFAULT",
                False,
                asset_library_type="ESSENTIALS",
                asset_library_identifier="",
                relative_asset_identifier=r"brushes\\essentials_brushes-mesh_texture.blend\\Brush\\Paint Hard Pressure",
            )
            paint_settings.size = 25
            paint_settings.color = [0, 0, 0]
            bpy.ops.ed.undo_push(message="Push Undo")
            return {"FINISHED"}

        if self.run_count > 20:  # 最多等待20次
            return {"CANCELLED"}
        self.run_count += 1
        return {"RUNNING_MODAL"}


class DrawImageMask(bpy.types.Operator, PublicPoll, SwitchPaint):
    bl_idname = "bas.draw_mask"
    bl_label = "Draw Mask"

    def invoke(self, context, event):
        bpy.ops.ed.undo_push(message="Push Undo")
        space = context.space_data

        image = get_edit_main_image(context)

        print(self.bl_idname, f"绘制{image.name}")
        if image.blender_ai_studio_property.is_mask_image:
            self.report({"ERROR"}, f"出现了错误，当前图片为遮罩图片,无法再进行绘制")
            return {"CANCELLED"}
        image.use_fake_user = True
        scene_prop = context.scene.blender_ai_studio_property

        new_name = png_name_suffix(image.name, "_mask")

        mask_image = image.copy()
        mask_image.use_fake_user = True
        try:
            if not mask_image.packed_file:
                mask_image.pack()
        except RuntimeError as e:
            print("pack error", e)
        mask_image.filepath = ""
        mask_image.name = new_name

        mi = scene_prop.mask_images.add()  # 新创建一个mask图
        mi.name = new_name
        mi.image = mask_image

        aip = mask_image.blender_ai_studio_property
        aip.is_mask_image = True
        aip.origin_image = image
        if mask_image is None:
            self.report({"ERROR"}, "Can't create mask image")
            return {"CANCELLED"}

        aip = mask_image.blender_ai_studio_property
        aip.is_edit_mask_image = True
        space.image = mask_image

        return self.start_switch(context)


class EditImageMask(bpy.types.Operator, PublicPoll, SwitchPaint):
    bl_idname = "bas.edit_mask"
    bl_label = "Edit Mask"

    def invoke(self, context, event):
        mask_image = getattr(context, "image", None)
        if mask_image:
            aip = mask_image.blender_ai_studio_property
            aip.is_edit_mask_image = True
            context.space_data.image = mask_image
        return self.start_switch(context)


class ApplyImageMask(bpy.types.Operator, PublicPoll):
    bl_idname = "bas.apply_image_mask"
    bl_translation_context = OPS_TCTX
    bl_label = "Apply Image Mask"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        space = context.space_data
        image = getattr(space, "image", None)
        return image and image.blender_ai_studio_property.is_mask_image

    def execute(self, context):
        space = context.space_data
        image = getattr(space, "image")
        print(self.bl_idname, image.name)
        bpy.ops.image.save("EXEC_DEFAULT", False)
        refresh_image_preview(image)
        image.use_fake_user = True
        if image.preview:
            image.preview.reload()

        aip = image.blender_ai_studio_property
        oii = context.scene.blender_ai_studio_property

        aip.is_edit_mask_image = False
        space.image = image
        space.ui_mode = "VIEW"
        for index, m in enumerate(oii.mask_images):
            if m.image == image:
                oii.mask_index = index
                continue
        return {"FINISHED"}


class SelectMask(bpy.types.Operator, PublicPoll):
    bl_idname = "bas.select_mask"
    bl_translation_context = OPS_TCTX
    bl_label = "Select Mask"
    bl_options = {"REGISTER"}

    index: bpy.props.IntProperty()

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
        context.scene.blender_ai_studio_property.clear_invalid_data()
        return context.window_manager.invoke_popup(self)

    def execute(self, context):
        space = context.space_data
        image = getattr(space, "image", None)
        oii = context.scene.blender_ai_studio_property
        print(self.bl_idname, self.index, image)

        oii.mask_index = self.index
        # if space.ui_mode == "PAINT":
        space.image = oii.active_mask
        return {"FINISHED"}

    def draw(self, context):
        layout = self.layout
        self.draw_select_mask(context, layout)

    @staticmethod
    def draw_select_mask(context, layout, use_box=False):
        column = layout.column(align=True)
        column.label(text="Mask History")
        column.operator_context = "EXEC_DEFAULT"
        oii = context.scene.blender_ai_studio_property
        for index, m in enumerate(oii.mask_images):
            if m.image and m.image.preview:
                box = column.box() if use_box else column.column(align=True)
                box.template_icon(m.image.preview.icon_id, scale=6)
                row = box.row(align=True)
                ops = row.operator("bas.select_mask", text=m.image.name, icon="RESTRICT_SELECT_OFF", translate=False)
                ops.index = index
                ops = row.operator("bas.remove_mask", text="", icon="TRASH")
                ops.index = index
        if len(oii.mask_images) == 0:
            column.label(text="No mask available, please draw")


class RemoveMask(bpy.types.Operator, PublicPoll):
    bl_idname = "bas.remove_mask"
    bl_translation_context = OPS_TCTX
    bl_label = "Remove Mask"
    bl_description = "Remove mask image"
    bl_options = {"REGISTER"}
    index: bpy.props.IntProperty()

    def execute(self, context):
        active_image = context.space_data.image

        origin_image = get_edit_main_image(context)
        oii = context.scene.blender_ai_studio_property
        mask_image = oii.mask_images[self.index].image

        print(self.bl_idname, self.index, origin_image)

        if active_image == mask_image:
            setattr(context.space_data, "image", origin_image)

        if origin_image and mask_image == origin_image:
            oi = mask_image.blender_ai_studio_property.origin_image
            if oi:
                setattr(context.space_data, "image", oi)
        oii.mask_images.remove(self.index)
        oii.mask_index = self.index

        return {"FINISHED"}
