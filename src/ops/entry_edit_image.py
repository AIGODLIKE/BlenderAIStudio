import bpy

from ..i18n.translations.zh_HANS import OPS_TCTX
from ..ui import AIStudioImagePanel
from ..utils.area import find_image_editor_areas


class EntryEditImage(bpy.types.Operator):
    bl_idname = "bas.entry_edit_image"
    bl_label = "Entry Edit Image"
    bl_translation_context = OPS_TCTX
    count = 0

    @classmethod
    def poll(cls, context):
        space_data = context.space_data
        return space_data and space_data.image is not None

    def invoke(self, context, event):
        self.count = 0
        if space_date := context.space_data:
            if space_date.show_region_ui:
                return self.execute(context)
            else:
                space_date.show_region_ui = True

        context.window_manager.modal_handler_add(self)
        self._timer = context.window_manager.event_timer_add(1 / 30, window=context.window)
        return {"RUNNING_MODAL", "PASS_THROUGH"}

    def modal(self, context, event):
        # print(self.bl_idname, "modal", event.type, event.value)
        for area in find_image_editor_areas():
            area.tag_redraw()
        if event.type == "TIMER":
            if self.count < 10:
                self.exit(context)
                return self.execute(context)
        self.count += 1
        return {"PASS_THROUGH"}

    def execute(self, context):
        if space_date := context.space_data:
            if not space_date.show_region_ui:
                space_date.show_region_ui = True
        if area := context.area:
            area.tag_redraw()
        for region in context.area.regions:
            if region.type == "UI":
                count = 0
                while count < 10:
                    try:
                        bl_category = AIStudioImagePanel.bl_category
                        region.active_panel_category = bl_category
                        if region.active_panel_category == bl_category:
                            if area := context.area:
                                area.tag_redraw()
                            break
                    except AttributeError as _:
                        ...
                    finally:
                        count += 1
        if area := context.area:
            area.tag_redraw()
        return {"FINISHED"}

    def exit(self, context):
        context.window_manager.event_timer_remove(self._timer)
