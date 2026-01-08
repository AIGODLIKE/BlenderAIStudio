import bpy

from ..i18n.translations.zh_HANS import OPS_TCTX
from ..utils import png_name_suffix, refresh_image_preview


class DrawImageMask(bpy.types.Operator):
    bl_idname = "bas.draw_mask"
    bl_label = "Draw Mask"
    bl_options = {"REGISTER"}
    bl_translation_context = OPS_TCTX
    bl_description = "Mask"
    run_count: bpy.props.IntProperty(default=0)

    is_edit: bpy.props.BoolProperty(default=False)

    @classmethod
    def poll(cls, context):
        space = context.space_data
        image = getattr(space, "image", None)
        return image and not image.blender_ai_studio_property.is_mask_image

    def invoke(self, context, event):
        bpy.ops.ed.undo_push(message="Push Undo")
        space = context.space_data
        print(self.bl_idname)

        image = getattr(space, "image")
        image.use_fake_user = True
        scene_prop = context.scene.blender_ai_studio_property

        name = png_name_suffix(image.name, "_mask")

        if self.is_edit:
            mask_image = getattr(context, "image", None)
        else:
            mask_image = image.copy()
            mask_image.use_fake_user = True
            try:
                if not mask_image.packed_file:
                    mask_image.pack()
            except RuntimeError as e:
                print("pack error", e)
            mask_image.filepath = ""
            mask_image.name = name

            mi = scene_prop.mask_images.add()  # 新创建一个mask图
            mi.name = name
            mi.image = mask_image

            aip = mask_image.blender_ai_studio_property
            aip.is_mask_image = True
            aip.origin_image = image
        if mask_image is None:
            self.report({"ERROR"}, "Can't create mask image")
            return {"CANCELLED"}
        space.image = mask_image
        space.ui_mode = "PAINT"

        context.window_manager.modal_handler_add(self)
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
            paint_settings.size = 4
            paint_settings.color = [1, 0, 0]
            bpy.ops.ed.undo_push(message="Push Undo")
            return {"FINISHED"}

        if self.run_count > 20:  # 最多等待20次
            return {"CANCELLED"}
        self.run_count += 1
        return {"RUNNING_MODAL"}


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
        refresh_image_preview(image)
        image.use_fake_user = True
        if image.preview:
            image.preview.reload()

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
        if properties.remove:
            return "Remove Mask"
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
            ri = oii.mask_images[self.index].image
            if image and ri == image:
                oi = ri.blender_ai_studio_property.origin_image
                if oi:
                    setattr(context.space_data, "image", oi)
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
                ops.remove = False
                ops = row.operator("bas.select_mask", text="", icon="TRASH")
                ops.index = index
                ops.remove = True
        if len(oii.mask_images) == 0:
            column.label(text="No mask available, please draw")
