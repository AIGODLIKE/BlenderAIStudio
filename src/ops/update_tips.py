import bpy

from ..utils import get_pref


class UpdateTips(bpy.types.Operator):
    bl_idname = "bas.update_tips"
    bl_label = "BLenderAiStudio Update Tips"

    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_props_popup(**{"operator": self, "event": event})

    def execute(self, context):
        print(self.bl_idname, "exec")
        return {"FINISHED"}

    def draw(self, context):
        pref = get_pref()
        pref.draw_online_update(self.layout)
