import bpy

from .. import logger
from ..utils import get_pref, get_addon_version_str
from ..utils.async_request import PostRequestThread
from ..utils.device_info import get_all_devices
from ..utils.memory_info import format_memory_info


def collect_info():
    pref = get_pref()
    if pref.init_privacy and pref.collect_version_data:
        from ..studio.account import Account
        try:
            account = Account.get_instance()
            url = f"{account.service_url}/sys/report"

            headers = {
                "X-Auth-T": account.token,
                "Content-Type": "application/json",
            }

            payload = {
                "blenderVersion": bpy.app.version_string,
                "addonVersionString": get_addon_version_str(),
                **get_all_devices(),
                "memory": format_memory_info(),
            }

            def on_request_finished(result, error):
                if result:
                    logger.info("send collect_info finished")
                if error:
                    logger.error("send collect_info error: %s", error)

            PostRequestThread(url, on_request_finished, headers, payload).start()
        except Exception as e:
            logger.error("send collect_info error: %s", e)


def privacy_tips_popup():
    """当没有初始化隐私设置时弹出窗口进行设置"""
    pref = get_pref()
    if not pref.init_privacy:
        bpy.ops.bas.privacy_tips("INVOKE_DEFAULT")


class Privacy:
    init_privacy: bpy.props.BoolProperty(default=False, update=lambda self, context: collect_info(),
                                         name="Privacy settings have been initialized")
    collect_version_data: bpy.props.BoolProperty(
        default=True, name="Version Data",
        update=lambda self, context: collect_info(),
        description="Check this box and we will collect your plugin version, Blender version, and hardware information")
    save_generated_images_to_cloud: bpy.props.BoolProperty(
        default=True,
        name="Save images generated in stable mode to the cloud",
        description="we will retain a copy of the generated image in the cloud to prevent image file loss")

    def draw_privacy(self, layout):
        column = layout.column()

        column.prop(self, "collect_version_data")
        column.label(
            text="Check this box and we will collect your plugin version, Blender version, and hardware information")
        column.label(text="to better serve you")
        column.separator(type="LINE")
        # column.prop(self, "save_generated_images_to_cloud")
        # column.label(text="When using Stable Mode to generate images")
        # column.label(text="we will retain a copy of the generated image in the cloud to prevent image file loss")
        column.separator()
        column.label(text="You can also change this setting later in Preferences")
