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

        ai = context.scene.blender_ai_studio_property
        layout = self.layout
        if check_is_draw_mask(context):
            self.draw_mask(context, layout)
            return

        self.draw_image_info(context, layout)
        is_not_run = ai.running_state != "running"
        column = layout.column(align=True)
        column.enabled = is_not_run  # 在运行中时不允许修改
        bb = column.box()
        bb.label(text="Out Resolution:")
        bb.prop(ai, "resolution", text="")
        bb = column.box()
        bb.label(text="AI Edit Prompt", icon='TEXT')
        row = bb.row(align=True)
        row.prop(ai, "prompt", text="")
        row.operator("bas.prompt_edit", text="", icon="FILE_TEXT")

        col = layout.column(align=True)
        col.enabled = is_not_run  # 在运行中时不允许修改
        ai.draw_reference_images(context, col)
        col.separator(factor=1.5)
        self.draw_mask(context, col)
        col.separator(factor=3)
        self.draw_ai_edit_layout(context, col)
        if not is_not_run:
            co = col.column(align=True)
            co.alert = True
            co.label(text="During task execution, parameters cannot be modified")

        layout.separator(factor=1)
        self.draw_state(context, layout)

    @staticmethod
    def draw_mask(context, layout: bpy.types.UILayout):
        from bl_ui.properties_paint_common import UnifiedPaintPanel
        from ..utils import get_custom_icon
        from ..studio.ops import SelectMask
        is_draw_mask = check_is_draw_mask(context)
        is_paint_2d = check_is_paint_2d(context)

        ai = context.scene.blender_ai_studio_property

        def draw_row(r):
            if ai and ai.active_mask and not is_draw_mask:
                rr = r.row(align=True)
                rr.operator_context = "EXEC_DEFAULT"
                rr.operator("bas.select_mask", text="", icon="X").index = -1
            if ai and ai.mask_images:
                r.operator_context = "INVOKE_DEFAULT"
                r.operator("wm.call_menu", text="", icon="COLLAPSEMENU").name = "BAS_MT_select_mask_menu"

        scale_y = 1.2
        if is_draw_mask:
            box = layout.box()
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
            row.scale_y = scale_y
            row.operator("bas.apply_image_mask")
            draw_row(row)
            SelectMask.draw_select_mask(context, box.box())
        else:
            if ai.active_mask:
                box = layout.box()
            else:
                box = layout.column()

            args = {}
            if ai.active_mask:
                args["text"] = "Redraw mask"
            row = box.row(align=True)
            row.scale_y = scale_y
            row.operator("bas.draw_mask", icon="BRUSH_DATA", **args)

            draw_row(row)
            if ai and ai.active_mask and ai.active_mask.preview:
                box.template_icon(ai.active_mask.preview.icon_id, scale=5)
        return is_draw_mask

    @staticmethod
    def draw_image_info(context, layout: bpy.types.UILayout):
        image = context.space_data.image
        w, h = image.size[:]

        layout.column(heading="Image Info")
        box = layout.box()
        box.label(text=f"{image.name}")
        box.label(text=f"{bpy.app.translations.pgettext_iface('Image size')}(px): {w} x {h}")
        if w == 0 and h == 0:
            box.alert = True
            box.label(text="The image is empty", icon="ERROR")

    @staticmethod
    def draw_ai_edit_layout(context, layout: bpy.types.UILayout):
        ai = context.scene.blender_ai_studio_property

        col = layout.column(align=True)
        args = {"icon": "SHADERFX"}  # 编辑图片操作符的参数
        ril = len(ai.reference_images)  # 参考图片数量
        if ril != 0:
            ...
        elif ai.prompt == "":
            args["text"] = "Please enter the prompt"
            args["icon"] = "ERROR"
            col.enabled = False

        col.scale_y = 1.5
        col.operator("bas.apply_ai_edit_image", **args)
        layout.separator(factor=2)
        column = layout.column(align=True)
        column.scale_y = 1.5
        column.operator("bas.rerender_image")
        column.operator("bas.finalize_composite")

    @staticmethod
    def draw_state(context, layout: bpy.types.UILayout):
        oii = context.scene.blender_ai_studio_property
        column = layout.column(align=True)
        for text in (
                oii.running_operator,
                oii.running_state.title(),
                oii.running_message,
        ):
            if text:
                column.label(text=text)
        image = context.space_data.image
        if image == oii.origin_image:
            if gi := oii.generated_image:
                box = column.box()
                box.context_pointer_set("image", gi)
                if gi.preview:
                    box.template_icon(gi.preview.icon_id, scale=6)
                box.operator("bas.view_image", text="View Generated Image")
        elif image == oii.generated_image:
            if oi := oii.origin_image:
                box = column.box()
                box.context_pointer_set("image", oi)
                if oi.preview:
                    box.template_icon(oi.preview.icon_id, scale=6)
                box.operator("bas.view_image", text="View Origin Image")


class AIStudioHistoryPanel(bpy.types.Panel):
    bl_idname = "SDN_PT_BLENDER_AI_STUDIO_PT_History"
    bl_label = "Generate History"
    bl_description = "Generate History"
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "AIStudio"

    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        space_data = context.space_data
        return space_data and space_data.image is not None

    # def draw_header(self, context):
    #     oii = context.scene.blender_ai_studio_property
    #     text = bpy.app.translations.pgettext("History")
    #     self.layout.label(text=f"{text} {len(oii.history)}")

    def draw(self, context):
        oii = context.scene.blender_ai_studio_property
        layout = self.layout
        for h in reversed(oii.history[:]):
            h.draw_history(layout)
