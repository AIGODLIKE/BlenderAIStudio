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
    init_privacy: bpy.props.BoolProperty(default=False)
    collect_version_data: bpy.props.BoolProperty(default=False, name="Version Data",
                                                 description="勾选后我们将会收集Blender版本号及插件版本号")
    save_generated_images_to_cloud: bpy.props.BoolProperty(default=True, name="保留稳定模式生成的图片到云端",
                                                           description="勾选后将会将生成完成的图片保留到云端,避免生成图片丢失")

    def draw_privacy(self, layout):
        layout.prop(self, "collect_version_data")
        layout.label(text="勾选后我们将会收集您的插件版本及Blender版本信息")
        layout.label(text="用于更好的提供服务")

        layout.separator()

        layout.prop(self, "save_generated_images_to_cloud")
        layout.label(text="勾选后在使用稳定模式生成图片时")
        layout.label(text="我们将会保留一份生成的图片在云端，避免图片文件丢失")
        layout.separator()
        layout.label(text="稍后您也可以在偏好设置中更改")
