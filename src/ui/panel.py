import bpy
from bpy.app.translations import pgettext_iface as iface

from ..i18n import PANEL_TCTX
from ..online_update_addon import UpdateService
from ..preferences import AuthMode
from ..studio.config.model_registry import ModelRegistry
from ..utils import get_custom_icon, get_addon_version_str, get_pref, check_image_is_render_result
from ..utils.camear_info import get_camera_info


def check_is_edit_mask(context):
    image = context.space_data.image
    ip = image.blender_ai_studio_property
    is_draw_mask = image and ip.is_mask_image and ip.is_edit_mask_image
    return is_draw_mask


def check_is_paint_2d(context):
    from bl_ui.properties_paint_common import UnifiedPaintPanel

    mode = UnifiedPaintPanel.get_brush_mode(context)
    return mode == "PAINT_2D"


def draw_row(context, layout, ai):
    is_draw_mask = check_is_edit_mask(context)
    if ai and ai.active_mask and not is_draw_mask:
        rr = layout.row(align=True)
        rr.operator_context = "EXEC_DEFAULT"
        op = rr.operator("bas.remove_mask", text="", icon="X")
        op.index = -1
    if ai and ai.mask_images:
        layout.operator_context = "INVOKE_DEFAULT"
        layout.operator("wm.call_menu", text="", icon="COLLAPSEMENU").name = "BAS_MT_select_mask_menu"


scale_y = 1.2


def draw_dev_info(context, layout):
    if get_pref().use_dev_ui:
        image = context.space_data.image
        prop = image.blender_ai_studio_property

        box = layout.box()
        box.label(text="Dev Info")
        box.prop(prop, "is_mask_image")
        box.prop(prop, "is_edit_mask_image")
        box.prop(prop, "origin_image")
        box.prop(prop, "generated_images")


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
        if space_data and space_data.image is not None:
            ai = space_data.image.blender_ai_studio_property
            if not ai.is_edit_mask_image:
                return True

        return False

    def draw(self, context):
        ai = context.scene.blender_ai_studio_property

        layout = self.layout

        draw_dev_info(context, layout)
        UpdateService.draw_update_info_panel(layout)  # 插件更新信息

        if check_is_edit_mask(context):
            self.draw_mask(context, layout)
            return

        main_image = context.space_data.image  # 主图
        if main_image:  # 如果当前图片为蒙版图片,就获取主图的信息
            iai = main_image.blender_ai_studio_property
            if iai.is_mask_image and iai.origin_image:
                main_image = iai.origin_image

        self.draw_image_info(context, layout, main_image)
        column = layout.column(align=True)
        bb = column.box()
        self.draw_model_parameters(context, bb)  # 动态绘制需要的参数
        col = layout.column(align=True)
        ai.draw_reference_images(context, col)
        col.separator(factor=1.5)
        self.draw_mask(context, col)
        col.separator(factor=3)
        self.draw_ai_edit_layout(context, col)
        self.draw_task_layout(context, layout)
        self.draw_image_switch(context, layout, main_image)

    @staticmethod
    def draw_image_switch(context, layout: bpy.types.UILayout, image):

        column = layout.column(align=True)
        ai = image.blender_ai_studio_property
        icon_size = 1
        items = [
            *(("View Generated Image", i.image) for i in ai.generated_images),
            ("View Origin Image", ai.origin_image),
        ]
        for text, i in items:
            if i:
                row = column.row()
                row.context_pointer_set("image", i)
                row.template_icon(i.preview.icon_id, scale=icon_size)
                row.operator("bas.view_image", text=text)

    @staticmethod
    def draw_image_info(context, layout: bpy.types.UILayout, image):
        """绘制图片的信息"""
        w, h = image.size[:]
        layout.column()

        box = layout.box()
        box.label(text="Image Info")

        box.label(text=f"{w}*{h} px(72dpi)", icon_value=get_custom_icon("image_info_resolution"))
        box.label(text=f"{image.name}", icon_value=get_custom_icon("image_info_vendor"))
        box.operator("image.clipboard_copy", icon="COPYDOWN", text="Copy image to clipboard")
        if check_image_is_render_result(image):
            box.label(text="Image is render result")
        elif w == 0 and h == 0:
            box.alert = True
            box.label(text="The image is empty", icon="ERROR")

    @staticmethod
    def draw_ai_edit_layout(context, layout: bpy.types.UILayout):
        ai = context.scene.blender_ai_studio_property
        pref = get_pref()

        column = layout.box().column(align=True)

        if pref.account_auth_mode == AuthMode.ACCOUNT.value:
            points = ai.get_points_consumption(context) * ai.batch_count
            points_consumption = bpy.app.translations.pgettext("(%s/use)") % points
            column.label(text=bpy.app.translations.pgettext("AI Edit") + points_consumption)

        if not pref.disable_system_prompt:
            # 没禁用才显示这些
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

    @staticmethod
    def draw_task_layout(context, layout: bpy.types.UILayout):
        """绘制生成中的任务"""
        ai = context.scene.blender_ai_studio_property
        for i in ai.running_task_list:
            layout.separator(factor=1)
            i.draw_task(context, layout)

    @staticmethod
    def draw_model_parameters(context, layout: bpy.types.UILayout):
        """动态绘制模型所需的参数"""
        ai = context.scene.blender_ai_studio_property
        model_register = ModelRegistry.get_instance()
        pref = get_pref()

        column = layout.column()
        pref.draw_account(column)

        row = column.row(align=True)
        row.prop(ai, "model_name")
        pref.have_input_api_key(context, column)

        spt = {}
        if bpy.app.version >= (4, 2, 0):
            spt["type"] = "LINE"
        column.separator(**spt)

        try:
            model = model_register.get_model(ai.model_name)
            for param in model.parameters:
                name = param.get("name", None)
                if draw_func := getattr(AIStudioImagePanel, f"draw_{name}", None):
                    draw_func(ai, column)
                elif pref.use_dev_ui:
                    column.label(text=f'{name}还没有绘制')
            AIStudioImagePanel.draw_batch_count(ai, column)
        except ValueError:
            ...

    @staticmethod
    def draw_batch_count(ai, layout: bpy.types.UILayout):
        """绘制批量数量"""
        row = layout.row(align=True)
        # row.label(text="", icon_value=get_custom_icon("aspect_ratio"))
        row.prop(ai, "batch_count", text="")

    @staticmethod
    def draw_aspect_ratio(ai, layout: bpy.types.UILayout):
        """绘制比例"""
        row = layout.row(align=True)
        row.label(text="", icon_value=get_custom_icon("aspect_ratio"))
        row.prop(ai, "aspect_ratio", text="")

    @staticmethod
    def draw_resolution(ai, layout: bpy.types.UILayout):
        row = layout.row(align=True)
        row.label(text="", icon_value=get_custom_icon("resolution"))
        row.prop(ai, "resolution", text="")

    @staticmethod
    def draw_size(ai, layout: bpy.types.UILayout):
        row = layout.row(align=True)
        row.label(text="", icon_value=get_custom_icon("resolution"))
        row.prop(ai, "size", text="")

    @staticmethod
    def draw_quality(ai, layout: bpy.types.UILayout):
        row = layout.row(align=True)
        row.label(text="", icon_value=get_custom_icon("quality"))
        row.prop(ai, "quality", text="")

    @staticmethod
    def draw_background(ai, layout: bpy.types.UILayout):
        row = layout.row(align=True)
        row.label(text="", icon_value=get_custom_icon("background"))
        row.prop(ai, "background", text="")

    @staticmethod
    def draw_size_config(ai, layout: bpy.types.UILayout):
        """aspect_ratio = size_config"""
        AIStudioImagePanel.draw_aspect_ratio(ai, layout)

    @staticmethod
    def draw_prompt(ai, layout: bpy.types.UILayout):
        layout.label(text="Edit Prompt", icon="TEXT")
        row = layout.row(align=True)
        row.prop(ai, "prompt", text="")
        row.operator("bas.prompt_edit", text="", icon="FILE_TEXT")

    @staticmethod
    def draw_mask(context, layout: bpy.types.UILayout):

        # layout.label(text="draw_mask")

        ai = context.scene.blender_ai_studio_property

        active_image = context.space_data.image
        if active_image:  # 一般不会出现这个问题
            ai_i = active_image.blender_ai_studio_property
            if ai_i.is_mask_image and active_image != ai.active_mask and ai_i.origin_image is None:
                layout.label(text="未找到遮罩的原图,出现了奇怪的错误！！")
        active_mask = ai.active_mask

        if active_mask:
            box = layout.box()
        else:
            box = layout.column()

        args = {}
        if active_mask:
            args["text"] = "Redraw mask"
        row = box.row(align=True)
        row.scale_y = scale_y
        row.operator("bas.draw_mask", icon="BRUSH_DATA", **args)
        if active_mask:
            row.context_pointer_set("image", active_mask)
            row.operator("bas.edit_mask", icon="IMAGE_RGB_ALPHA", text="Edit mask")

        draw_row(context, row, ai)
        if ai and active_mask:
            i = active_mask
            if context.space_data.image == i:
                i = active_mask.blender_ai_studio_property.origin_image
            if i and i.preview:
                box.template_icon(i.preview.icon_id, scale=5)


class AIStudioEditMaskPanel(bpy.types.Panel):
    bl_idname = "SDN_PT_BLENDER_AI_STUDIO_PT_Edit_Mask"
    bl_label = f"Blender AI Studio Edit Mask {get_addon_version_str()}"
    bl_translation_context = PANEL_TCTX
    bl_space_type = "IMAGE_EDITOR"
    bl_region_type = "UI"
    bl_category = "AIStudio"

    @classmethod
    def poll(cls, context):
        space_data = context.space_data
        if space_data and space_data.image is not None:
            ai = space_data.image.blender_ai_studio_property
            if ai.is_edit_mask_image:
                return True
        return False

    def draw(self, context):
        from bl_ui.properties_paint_common import UnifiedPaintPanel
        from ..ops import SelectMask

        layout = self.layout
        draw_dev_info(context, layout)
        layout.label(text="Edit Mask")

        is_paint_2d = check_is_paint_2d(context)

        ai = context.scene.blender_ai_studio_property

        box = layout.box()
        if is_paint_2d:  # 绘制笔刷大小和颜色
            if paint_settings := getattr(UnifiedPaintPanel.paint_settings(context), "unified_paint_settings", None):
                box.prop(paint_settings, "size")
                box.prop(paint_settings, "color")
        # box.template_icon(get_custom_icon("draw_mask_example"), scale=6)
        if not is_paint_2d:
            ops = box.operator("wm.context_set_string", text="Continue drawing", icon="BRUSH_DATA")
            ops.data_path = "space_data.ui_mode"
            ops.value = "PAINT"
        row = box.row(align=True)
        row.scale_y = scale_y
        row.operator("bas.apply_image_mask", icon="CHECKMARK")
        SelectMask.draw_select_mask(context, box.box())


class AIStudioScenePanel(bpy.types.Panel):
    """场景属性中的 Blender AI Studio 设置"""
    bl_idname = "SDN_PT_BLENDER_AI_STUDIO_PT_Scene"
    bl_translation_context = PANEL_TCTX
    bl_label = "Blender AI Studio"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "data"

    @classmethod
    def poll(cls, context):
        return context.object and context.object.type == "CAMERA"

    def draw(self, context):
        layout = self.layout
        ai = context.scene.blender_ai_studio_property
        layout.prop(ai, "orientation_reference_object", text=iface("Orientation Reference Object"))
        if ai.orientation_reference_object:
            layout.label(text=iface(
                "Camera info will use this object as origin and its forward direction as reference for relative azimuth and elevation"),
                icon="INFO")
            if info := get_camera_info(context):
                layout.label(text=info)


class AIStudioHistoryPanel(bpy.types.Panel):
    bl_idname = "SDN_PT_BLENDER_AI_STUDIO_PT_History"
    bl_label = ""
    bl_description = "Generate History"
    bl_space_type = "IMAGE_EDITOR"
    bl_region_type = "UI"
    bl_category = "AIStudio"

    bl_options = {"DEFAULT_CLOSED", "HEADER_LAYOUT_EXPAND"}

    @classmethod
    def poll(cls, context):
        space_data = context.space_data
        return space_data and space_data.image is not None

    def draw_header(self, context):
        oii = context.scene.blender_ai_studio_property

        row = self.layout.row()
        text = bpy.app.translations.pgettext("Generate History")
        row.label(text=f"{text} {len(oii.edit_history)}")
        row.separator()
        row.operator("bas.clear_history", icon="X", text="", emboss=False)
        row.separator()

    def draw(self, context):
        oii = context.scene.blender_ai_studio_property
        layout = self.layout
        draw_dev_info(context, layout)

        rl = list(oii.running_task_list)
        if rl:
            text = iface("%s Item is currently being generated")
            layout.label(text=text % len(rl))
        items = oii.edit_history[:]
        il = len(items)
        for index, h in enumerate(reversed(items)):
            if h.is_running:
                ...
            else:
                h.draw_history(context, layout, il - index - 1)
        if len(oii.edit_history) == 0:
            layout.label(text="No history available at the moment")
