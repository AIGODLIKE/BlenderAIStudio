import tempfile
from enum import Enum

import bpy

from ..i18n import PROP_TCTX
from ..online_update_addon import UpdateService
from ... import __package__ as base_name
from .online_update import OnlineUpdate
from bpy.app.translations import pgettext_iface as iface
translation_context = {}

if bpy.app.version >= (4, 0, 0):
    translation_context["translation_context"] = PROP_TCTX


class AuthMode(Enum):
    ACCOUNT = "Backup Mode"
    API = "API Key Mode"


class BlenderAIStudioPref(bpy.types.AddonPreferences, OnlineUpdate):
    bl_idname = base_name
    ui_pre_scale: bpy.props.FloatProperty(
        name="UI Pre Scale Factor",
        default=0.5,
        min=0.2,
        max=10,
        **translation_context,
    )
    ui_offset: bpy.props.FloatVectorProperty(
        name="UI Offset",
        default=(0, 200),
        min=0,
        max=4096,
        step=1,
        size=2,
        **translation_context,
    )
    output_cache_dir: bpy.props.StringProperty(
        name="Output Cache Directory",
        subtype="DIR_PATH",
        default=tempfile.gettempdir(),
        **translation_context,
    )
    account_auth_mode: bpy.props.EnumProperty(
        name="Account Auth Mode",
        items=[(item.value, item.value, "") for item in AuthMode],
        **translation_context,
    )
    nano_banana_api: bpy.props.StringProperty(
        name="Nano Banana API Key",
        subtype="PASSWORD",
    )
    page_type: bpy.props.EnumProperty(
        name="Page Type",
        items=[
            ("SETTING", "Setting", ""),
            ("ONLINE_UPDATE", "Update Addon", ""),
        ],
        **translation_context,
    )

    @property
    def is_backup_mode(self):  # 是稳定模式
        return self.account_auth_mode == "Backup Mode"

    def set_ui_offset(self, value):
        self.ui_offset = value
        bpy.context.preferences.use_preferences_save = True

    def set_account_auth_mode(self, value):
        self.account_auth_mode = value
        bpy.context.preferences.use_preferences_save = True

    def draw(self, context):
        layout = self.layout
        column = layout.column()
        column.row(align=True).prop(self, "page_type", expand=True)
        if draw_func := getattr(self, f"draw_{self.page_type.lower()}", None):
            draw_func(column.box())

    def draw_setting(self, layout):
        layout.prop(self, "ui_pre_scale")
        layout.prop(self, "ui_offset")
        layout.prop(self, "output_cache_dir")
        self.draw_api(layout.box())

    def draw_online_update(self, layout):
        UpdateService.draw_update_info(layout)

    def draw_api(self, layout):
        from ..studio.account import Account
        layout.label(text="Service")
        layout.prop(self, "account_auth_mode", text="Operating Mode", )
        if self.is_backup_mode:
            account = Account.get_instance()
            if account.is_logged_in():
                layout.label(text=iface("Logged in") + account.nickname)
                layout.label(text=iface("Credits : %s") % account.credits)
                layout.operator("bas.logout_account_auth")
            elif account.is_waiting_for_login():
                layout.label(text="Waiting for login...")
            else:
                layout.label(text="Not logged in")
                layout.operator("bas.login_account_auth")
        else:
            layout.prop(self, "nano_banana_api")
            if self.nano_banana_api == "":
                layout.label(text="Please input your API Key")


def register():
    bpy.utils.register_class(BlenderAIStudioPref)


def unregister():
    bpy.utils.unregister_class(BlenderAIStudioPref)
