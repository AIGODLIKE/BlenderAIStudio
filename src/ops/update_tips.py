import bpy

from ..utils import get_pref


class UpdateTips(bpy.types.Operator):
    bl_idname = "bas.update_tips"
    bl_label = "BLenderAiStudio Update Tips"

    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_popup(self)

    def execute(self, context):
        return {"FINISHED"}

    def draw(self, context):
        layout = self.layout
        column = layout.column()
        column.label(text=self.bl_label)
        pref = get_pref()
        pref.draw_online_update(column)
