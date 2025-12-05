import bpy

from ..i18n import PANEL_TCTX
from ..studio.ops import AIStudioEntry


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
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "AIStudio"

    @classmethod
    def poll(cls, context):
        space_data = context.space_data
        return space_data and space_data.image is not None

    def draw(self, context):
        from ..i18n import PROP_TCTX

        ai = context.scene.blender_ai_studio_property
        layout = self.layout
        if check_is_draw_mask(context):
            self.draw_mask(context, layout)
            return

        self.draw_image_info(context, layout)

        box = layout.box()
        box.label(text="Prompt", icon='TEXT', text_ctxt=PROP_TCTX)
        row = box.row(align=True)
        row.prop(ai, "prompt", text="")
        row.operator("bas.prompt_edit", text="", icon="FILE_TEXT")

        ai.draw_reference_images(context, layout)
        self.draw_mask(context, layout)

        layout.operator("bas.generate_image")
        layout.operator("bas.rerender_image")
        layout.operator("bas.finalize_composite")

    @staticmethod
    def draw_mask(context, layout: bpy.types.UILayout):
        from bl_ui.properties_paint_common import UnifiedPaintPanel
        from ..utils import get_custom_icon
        from ..studio.ops import SelectMask
        mode = UnifiedPaintPanel.get_brush_mode(context)
        is_draw_mask = check_is_draw_mask(context)
        is_paint_2d = check_is_paint_2d(context)

        oii = context.scene.blender_ai_studio_property

        box = layout.box()

        # image = context.space_data.image
        # ip = image.blender_ai_studio_property
        # box.prop(ip, "is_mask_image")
        # box.label(text=mode)
        def draw_row(r):
            if oii and oii.active_mask:
                rr = r.row(align=True)
                rr.operator_context = "EXEC_DEFAULT"
                rr.operator("bas.select_mask", text="", icon="X").index = -1
            if oii and oii.mask_images:
                r.operator_context = "INVOKE_DEFAULT"
                # r.operator("bas.select_mask", text="", icon="COLLAPSEMENU")
                r.operator("wm.call_menu", text="", icon="COLLAPSEMENU").name = "BAS_MT_select_mask_menu"

        if is_draw_mask:
            if is_paint_2d:  # 绘制笔刷大小和颜色
                paint_settings = UnifiedPaintPanel.paint_settings(context).unified_paint_settings
                if paint_settings:
                    box.prop(paint_settings, "size")
                    box.prop(paint_settings, "color")
            box.template_icon(get_custom_icon("img"), scale=6)
            if not is_paint_2d:
                ops = box.operator("wm.context_set_string", text="Paint 2D")
                ops.data_path = "space_data.ui_mode"
                ops.value = "PAINT"
            row = box.row(align=True)
            row.operator("bas.apply_image_mask")
            draw_row(row)
            SelectMask.draw_select_mask(context, box)
        else:
            row = box.row(align=True)
            row.scale_y = 2
            row.operator("bas.draw_mask")

            draw_row(row)
            if oii and oii.active_mask and oii.active_mask.preview:
                box.template_icon(oii.active_mask.preview.icon_id, scale=5)
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
