import bpy

from ..utils import get_pref


def collect_info():
    pref = get_pref()
    if pref.init_privacy and pref.collect_version_data:
        print("collect_info")


def privacy_tips_popup():
    """当没有初始化隐私设置时弹出窗口进行设置"""
    pref = get_pref()
    if not pref.init_privacy:
        bpy.ops.bas.privacy_tips("INVOKE_DEFAULT")


class Privacy:
    init_privacy: bpy.props.BoolProperty(default=False, )
    collect_version_data: bpy.props.BoolProperty(default=False, name="Version Data",
                                                 description="By checking this box, we will collect your plugin version and Blender version information")
    save_generated_images_to_cloud: bpy.props.BoolProperty(default=True,
                                                           name="Save images generated in stable mode to the cloud",
                                                           description="we will retain a copy of the generated image in the cloud to prevent image file loss")

    def draw_privacy(self, layout):
        column = layout.column()

        column.prop(self, "collect_version_data")
        column.label(text="By checking this box, we will collect your plugin version and Blender version information")
        column.label(text="to better serve you")
        column.separator(type="LINE")
        column.prop(self, "save_generated_images_to_cloud")
        column.label(text="When using Stable Mode to generate images")
        column.label(text="we will retain a copy of the generated image in the cloud to prevent image file loss")
        column.separator()
        column.label(text="You can also change this setting later in Preferences")
