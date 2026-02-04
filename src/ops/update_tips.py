import bpy

from ..online_update_addon import UpdateService, OnlineUpdateAddon
from ..utils import get_pref


class UpdateTips(bpy.types.Operator):
    bl_idname = "bas.update_tips"
    bl_label = "BLenderAiStudio Update Tips"

    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_props_dialog(**{"operator": self, "width": 350})

    def execute(self, context):
        print(self.bl_idname, "exec")
        if last_version_data := UpdateService.get_last_version_data():
            if not OnlineUpdateAddon.update_info:
                last_version = last_version_data.get("version", "unknown")
                md5 = last_version_data.get("md5", "unknown")
                bpy.ops.bas.online_update_addon(version=last_version, md5=md5)
            return {"FINISHED"}
        else:
            return {"CANCELLED"}

    def draw(self, context):
        pref = get_pref()
        pref.draw_online_update(self.layout)
