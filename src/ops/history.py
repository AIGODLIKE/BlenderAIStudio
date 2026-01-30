import json
from threading import Thread

import bpy

from ..i18n.translations.zh_HANS import OPS_TCTX
from ..utils import load_image
from ..utils.ctypes.window import foreground_image_edit_window


class ViewImage(bpy.types.Operator):
    bl_idname = "bas.view_image"
    bl_label = "View Image"
    bl_translation_context = OPS_TCTX
    bl_options = {"REGISTER"}
    bl_description = "View image"

    @classmethod
    def poll(cls, context):
        return hasattr(context.space_data, "image")

    def execute(self, context):
        image = getattr(context, "image", None)
        if not image:
            self.report({"ERROR"}, "No image")
            return {"CANCELLED"}
        if image.preview:
            image.preview.reload()
        else:
            image.preview_ensure()
        setattr(context.space_data, "image", image)
        return {"FINISHED"}


class RestoreHistory(bpy.types.Operator):
    bl_idname = "bas.restore_history"
    bl_label = "Restore History"
    bl_translation_context = OPS_TCTX
    bl_options = {"REGISTER"}
    bl_description = "Restore ai edit history"

    @classmethod
    def poll(cls, context):
        return hasattr(context, "history")

    @classmethod
    def description(cls, context, properties):
        history = getattr(context, "history")
        if history:
            text = bpy.app.translations.pgettext("Restore ai edit history")
            return f"{text}\n%s" % history.more_history_information
        return "Restore ai edit history"

    def execute(self, context):
        history = getattr(context, "history")
        print(self.bl_idname, history)
        history.restore_history(context)
        return {"FINISHED"}


class OpenImageInNewWindow(bpy.types.Operator):
    bl_idname = "bas.open_image_in_new_window"
    bl_label = "Open Image In New Window"
    bl_translation_context = OPS_TCTX
    bl_options = {"REGISTER"}
    bl_description = "Open image in new window"

    image_path: bpy.props.StringProperty()
    data: bpy.props.StringProperty()

    run_count: bpy.props.IntProperty(default=0)

    @staticmethod
    def get_image_window(context):
        wm = context.window_manager

        # 获取一个新窗口
        if len(wm.windows) > 1:
            last_window = wm.windows[-1]
            if len(last_window.screen.areas[:]) == 1:
                last_area = last_window.screen.areas[0]
                if last_area.type == "IMAGE_EDITOR":
                    return last_window
        return None

    def invoke(self, context, event):
        self.load_data(context)
        image_window = self.get_image_window(context)
        if image_window:
            Thread(target=foreground_image_edit_window, daemon=True).start()
            return self.execute(context)
        else:
            bpy.ops.wm.window_new("EXEC_DEFAULT", False)
            last_window = bpy.context.window_manager.windows[-1]
            last_window.screen.areas[0].type = "IMAGE_EDITOR"
            context.window_manager.modal_handler_add(self)
            context.window_manager.event_timer_add(1 / 60, window=context.window)
            return {"RUNNING_MODAL", "PASS_THROUGH"}

    def load_data(self, context):
        try:
            data = json.loads(self.data)
            metadata = data.get("metadata", None)
            if metadata:
                aspect_ratio = metadata.get("aspect_ratio", "1:1")
                oii = context.scene.blender_ai_studio_property
                resolution = metadata.get("resolution", "1K")
                oii.aspect_ratio = aspect_ratio
                oii.resolution = resolution
        except Exception as e:
            import traceback
            traceback.print_exc()
            traceback.print_stack()
            print(e)
            print("load_data error", self.data)

    def modal(self, context, event):
        return self.execute(context)

    def execute(self, context):
        try:
            image_window = self.get_image_window(context)
            if not image_window:
                self.report({"ERROR"}, "No image window")
                return {"CANCELLED"}
            if image_window:
                image = load_image(self.image_path)
                if image is None:
                    self.report({"ERROR"}, "No image" + self.image_path)
                    return {"CANCELLED"}
                for area in image_window.screen.areas:
                    if area.type == "IMAGE_EDITOR":
                        for space in area.spaces:
                            if space.type == "IMAGE_EDITOR":
                                space.image = image
                                space.show_region_ui = True
                                region = area.regions[4]
                                if region.active_panel_category == "UNSUPPORTED":  # 如果还是不支持说明还没被渲染或初始化,再等待多一会
                                    self.run_count += 1
                                    if self.run_count > 20:  # 最多等待20次
                                        self.report({"ERROR"}, "No image area")
                                        return {"CANCELLED"}
                                    return {"RUNNING_MODAL"}
                                region.active_panel_category = "AIStudio"  # 设置活动面板
                                # with context.temp_override(window=image_window, area=area, region=region):
                                #     bpy.ops.image.view_all(**{"fit_view": True})
                                #     bpy.ops.image.view_all(fit_view=True)
                                return {"FINISHED"}
                self.report({"ERROR"}, "No image area")
        except Exception as e:
            print(e)
            import traceback
            traceback.print_exc()
            traceback.print_stack()
            self.report({"ERROR"}, str(e.args))
        return {"CANCELLED"}


class RemoveHistory(bpy.types.Operator):
    bl_idname = "bas.remove_history"
    bl_label = "Remove History"
    bl_translation_context = OPS_TCTX

    index: bpy.props.IntProperty()

    def execute(self, context):
        oii = context.scene.blender_ai_studio_property
        index = self.index
        oii.edit_history.remove(index)
        return {"FINISHED"}


class ClearHistory(bpy.types.Operator):
    bl_idname = "bas.clear_history"
    bl_label = "Clear All History"
    bl_description = "Clear All History"
    bl_translation_context = OPS_TCTX

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event,
                                                     title=self.bl_description,
                                                     message="Are you sure you want to clear all history?")

    def execute(self, context):
        """
        可能会无限循环
        """
        aoo = context.scene.blender_ai_studio_property
        while True:
            is_r = False
            for index,i in  enumerate(aoo.edit_history):
                if i.running_state != "running":
                    aoo.edit_history.remove(index)
                    is_r = True
                    continue
            if not is_r:
                if context.area:
                    context.area.tag_redraw()
                return {"FINISHED"}

