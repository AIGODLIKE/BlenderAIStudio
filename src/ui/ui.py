import bpy

from ..i18n import PANEL_TCTX
from ..studio import AIStudioEntry


class AIStudioPanel(bpy.types.Panel):
    bl_idname = "SDN_PT_BLENDER_AI_STUDIO"
    bl_translation_context = PANEL_TCTX
    bl_label = "Blender AI Studio"
    bl_description = ""
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AIStudio"

    def draw(self, context):
        layout = self.layout
        layout.label(text="Blender AI Studio")
        layout.operator(AIStudioEntry.bl_idname)


def check_is_draw_mask(context):
    image = context.space_data.image
    ip = image.blender_ai_studio_property
    is_draw_mask = image and ip.is_mask_image
    return is_draw_mask


def check_is_paint_2d(context):
    from bl_ui.properties_paint_common import UnifiedPaintPanel
    mode = UnifiedPaintPanel.get_brush_mode(context)
    return mode == 'PAINT_2D'


class AIStudioImagePanel(bpy.types.Panel):
    bl_idname = "SDN_PT_BLENDER_AI_STUDIO_PT_Image"
    bl_translation_context = PANEL_TCTX
    bl_label = "Blender AI Studio"
    bl_description = ""
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "AIStudio"

    @classmethod
    def poll(cls, context):
        space_data = context.space_data
        return space_data and space_data.image is not None

    def draw(self, context):
        ai = context.scene.blender_ai_studio_property
        layout = self.layout
        if check_is_draw_mask(context):
            self.draw_mask(context, layout)
            return

        self.draw_image_info(context, layout)

        box = layout.box()
        box.label(text="Prompt", icon='TEXT')
        box.prop(ai, "prompt", text="")

        ai.draw_reference_images(context, layout)
        self.draw_mask(context, layout)

        layout.operator("bas.generate_image")

    @staticmethod
    def draw_mask(context, layout: bpy.types.UILayout):
        from bl_ui.properties_paint_common import UnifiedPaintPanel
        from ..utils import get_custom_icon
        image = context.space_data.image
        ip = image.blender_ai_studio_property
        mode = UnifiedPaintPanel.get_brush_mode(context)
        is_draw_mask = check_is_draw_mask(context)
        is_paint_2d = check_is_paint_2d(context)

        layout.prop(ip, "is_mask_image")
        layout.label(text=mode)
        if is_draw_mask:
            if is_paint_2d:  # 绘制笔刷大小和颜色
                paint_settings = UnifiedPaintPanel.paint_settings(context).unified_paint_settings
                if paint_settings:
                    layout.prop(paint_settings, "size")
                    layout.prop(paint_settings, "color")
            img = get_custom_icon("img")
            layout.template_icon(img, scale=5)
            layout.operator("bas.apply_edit_image")
            if not is_paint_2d:
                ops = layout.operator("wm.context_set_string", text="Paint 2D")
                ops.data_path = "space_data.ui_mode"
                ops.value = "PAINT"
        else:
            layout.operator("bas.draw_mask")

        oii = context.scene.blender_ai_studio_property
        for m in oii.mask_images:
            if m.image:
                layout.template_icon(m.image.preview.icon_id, scale=5)
                layout.label(text=m.name)
        return is_draw_mask

    @staticmethod
    def draw_image_info(context, layout: bpy.types.UILayout):
        image = context.space_data.image
        ai = context.scene.blender_ai_studio_property
        w, h = image.size[:]

        layout.column(heading="Image Info")
        box = layout.box()
        box.label(text=f"{image.name}")
        box.label(text=f"{bpy.app.translations.pgettext_iface('Image size')}(px): {w} x {h}")
        split = box.split(factor=0.2)
        split.label(text="Out Resolution")
        split.prop(ai, "resolution", text="")


class AIStudioHistoryPanel(bpy.types.Panel):
    bl_idname = "SDN_PT_BLENDER_AI_STUDIO_PT_History"
    bl_label = "History"
    bl_description = "生成历史"
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "AIStudio"

    # bl_options = {"HIDE_HEADER", "INSTANCED"}

    @classmethod
    def poll(cls, context):
        space_data = context.space_data
        return space_data and space_data.image is not None

    def draw(self, context):
        layout = self.layout

        space_data = context.space_data
        image = space_data.image
        layout.label(text="History")
