import bpy

from ..i18n import PANEL_TCTX
from ..online_update_addon import UpdateService
from ..utils import get_custom_icon, get_addon_version_str, get_pref


def check_is_draw_mask(context):
    image = context.space_data.image
    ip = image.blender_ai_studio_property
    is_draw_mask = image and ip.is_mask_image
    return is_draw_mask


def check_is_paint_2d(context):
    from bl_ui.properties_paint_common import UnifiedPaintPanel

    mode = UnifiedPaintPanel.get_brush_mode(context)
    return mode == "PAINT_2D"


class AIStudioImagePanel(bpy.types.Panel):
    bl_idname = "SDN_PT_BLENDER_AI_STUDIO_PT_Image"
    bl_translation_context = PANEL_TCTX
    bl_label = f"Blender AI Studio {get_addon_version_str()}"
    bl_space_type = "IMAGE_EDITOR"
    bl_region_type = "UI"
    bl_category = "AIStudio"

    @classmethod
    def poll(cls, context):
        space_data = context.space_data
        return space_data and space_data.image is not None

    def draw(self, context):
        ai = context.scene.blender_ai_studio_property
        layout = self.layout
        UpdateService.draw_update_info_panel(layout)
        if check_is_draw_mask(context):
            self.draw_mask(context, layout)
            return

        self.draw_image_info(context, layout)
        is_not_run = ai.running_state != "running"
        w, h = ai.get_out_resolution_px_by_aspect_ratio_and_resolution(context)
        column = layout.column(align=True)
        column.enabled = is_not_run  # 在运行中时不允许修改
        bb = column.box()
        row = bb.row(align=True)
        row.label(text="", icon_value=get_custom_icon("aspect_ratio"))
        row.prop(ai, "aspect_ratio", text="")
        # bb.label(text="Out Resolution:")
        row = bb.row(align=True)
        row.label(text="", icon_value=get_custom_icon("resolution"))
        row.prop(ai, "resolution", text="")
        bb.label(text=bpy.app.translations.pgettext_iface("Out Resolution(px):") + f"{w} x {h}")
        bb = column.box()
        bb.label(text="AI Edit Prompt", icon="TEXT")
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
        ai.draw_state(context, layout)

    @staticmethod
    def draw_mask(context, layout: bpy.types.UILayout):
        from bl_ui.properties_paint_common import UnifiedPaintPanel
        from ..utils import get_custom_icon
        from ..ops import SelectMask

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
                if paint_settings := getattr(UnifiedPaintPanel.paint_settings(context), "unified_paint_settings", None):
                    box.prop(paint_settings, "size")
                    box.prop(paint_settings, "color")
            box.template_icon(get_custom_icon("draw_mask_example"), scale=6)
            if not is_paint_2d:
                ops = box.operator("wm.context_set_string", text="Continue drawing", icon="BRUSH_DATA")
                ops.data_path = "space_data.ui_mode"
                ops.value = "PAINT"
            row = box.row(align=True)
            row.scale_y = scale_y
            row.operator("bas.apply_image_mask", icon="CHECKMARK")
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
            row.operator("bas.draw_mask", icon="BRUSH_DATA", **args).is_edit = False
            if ai.active_mask:
                row.context_pointer_set("image", ai.active_mask)
                row.operator("bas.draw_mask", icon="IMAGE_RGB_ALPHA", text="Edit mask").is_edit = True

            draw_row(row)
            if ai and ai.active_mask and ai.active_mask.preview:
                box.template_icon(ai.active_mask.preview.icon_id, scale=5)
        return is_draw_mask

    @staticmethod
    def draw_image_info(context, layout: bpy.types.UILayout):
        image = context.space_data.image
        w, h = image.size[:]

        layout.column()

        box = layout.box()
        box.label(text="Image Info")

        box.label(text=f"{w}*{h} px(72dpi)", icon_value=get_custom_icon("image_info_resolution"))
        box.label(text=f"{image.name}", icon_value=get_custom_icon("image_info_vendor"))
        if w == 0 and h == 0:
            box.alert = True
            box.label(text="The image is empty", icon="ERROR")
        box.operator("image.clipboard_copy", icon="COPYDOWN", text="Copy image to clipboard")

    @staticmethod
    def draw_ai_edit_layout(context, layout: bpy.types.UILayout):
        ai = context.scene.blender_ai_studio_property
        pref = get_pref()

        column = layout.box().column(align=True)
        
        if pref.account_auth_mode == "Backup Mode":
            points_consumption = bpy.app.translations.pgettext("(%s/use)") % ai.get_points_consumption(context)
            column.label(text=bpy.app.translations.pgettext("AI Edit") + points_consumption)

        row = column.row(align=True)
        row.scale_y = 1.2

        row.operator("bas.rerender_image", icon="RENDER_STILL")
        row.operator("bas.smart_fix", icon="RENDERLAYERS")

        row = column.row(align=True)
        row.scale_y = 2
        rr = row.row(align=True)
        args = {"text": "Render", "icon": "SHADERFX"}  # 编辑图片操作符的参数
        ril = len(ai.reference_images)  # 参考图片数量
        if ril != 0:
            ...
        elif ai.prompt == "":
            args["text"] = "Please enter the prompt"
            args["icon"] = "ERROR"
            rr.enabled = False
            rr.alert = True
        rr.operator("bas.apply_ai_edit_image", **args)
        # row.menu("BAS_MT_render_button_menu", icon='DOWNARROW_HLT', text="")


class AIStudioHistoryPanel(bpy.types.Panel):
    bl_idname = "SDN_PT_BLENDER_AI_STUDIO_PT_History"
    bl_label = "Generate History"
    bl_description = "Generate History"
    bl_space_type = "IMAGE_EDITOR"
    bl_region_type = "UI"
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
        items = oii.history[:]
        il = len(items)
        for index, h in enumerate(reversed(items)):
            h.draw_history(layout, il - index)
        if len(oii.history) == 0:
            layout.label(text="No history available at the moment")
