import bpy

from ..utils import get_pref


class PrivacyTips(bpy.types.Operator):
    """隐私提示"""
    bl_idname = "bas.privacy_tips"
    bl_label = "BLenderAiStudio Privacy Tips"

    def invoke(self, context, event):
        wm = context.window_manager
        pref = get_pref()
        pref.init_privacy = True
        return wm.invoke_props_dialog(**{"operator": self, "width": 350})

    def execute(self, context):
        print(self.bl_idname, "exec")
        from ..preferences.privacy import collect_info
        collect_info()
        return {"FINISHED"}

    def draw(self, context):
        pref = get_pref()
        pref.draw_privacy(self.layout)
