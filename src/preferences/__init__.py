import tempfile
from enum import Enum

import bpy
from bpy.app.translations import pgettext_iface as iface

from .api_key import ApiKey
from .online_update import OnlineUpdate
from .privacy import Privacy
from ..i18n import PROP_TCTX
from ..online_update_addon import UpdateService
from ... import __package__ as base_name

translation_context = {}

if bpy.app.version >= (4, 0, 0):
    translation_context["translation_context"] = PROP_TCTX


class AuthMode(Enum):
    """认证模式枚举

    value: 配置文件中使用的值（小写）
    display_name: UI 显示名称（支持翻译）
    """

    API = "api"
    ACCOUNT = "account"

    @property
    def display_name(self) -> str:
        """获取可翻译的显示名称"""
        if self == AuthMode.API:
            return "API Key Mode"
        elif self == AuthMode.ACCOUNT:
            return "Backup Mode"
        return self.value

    @classmethod
    def values(cls) -> list[str]:
        """获取所有值的元组"""
        return [item.value for item in list(cls)]


class PricingStrategy(Enum):
    BEST_SPEED = "bestSpeed"
    BEST_BALANCE = "bestPrice"

    @property
    def display_name(self) -> str:
        """获取可翻译的显示名称"""
        if self == PricingStrategy.BEST_SPEED:
            return "Best Speed"
        elif self == PricingStrategy.BEST_BALANCE:
            return "Best Balance"
        return self.value

    @classmethod
    def values(cls) -> list[str]:
        """获取所有值的元组"""
        return [item.value for item in list(cls)]


class BlenderAIStudioPref(bpy.types.AddonPreferences, OnlineUpdate, ApiKey, Privacy):
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
        items=[(item.value, item.display_name, "") for item in AuthMode],
        **translation_context,
    )
    page_type: bpy.props.EnumProperty(
        name="Page Type",
        items=[
            ("SETTING", "Setting", ""),
            ("DEV", "Dev Environment", ""),
            ("PRIVACY", "Privacy", ""),
            ("ONLINE_UPDATE", "Update Addon", ""),
        ],
        **translation_context,
    )

    @property
    def is_backup_mode(self):  # 是稳定模式
        return self.account_auth_mode == AuthMode.ACCOUNT.value

    @property
    def is_api_mode(self):
        return self.account_auth_mode == AuthMode.API.value

    def set_ui_offset(self, value):
        self.ui_offset = value
        bpy.context.preferences.use_preferences_save = True

    def set_account_auth_mode(self, value):
        self.account_auth_mode = value
        bpy.context.preferences.use_preferences_save = True

    account_pricing_strategy: bpy.props.EnumProperty(
        name="Account Pricing Strategy",
        items=[(item.value, item.display_name, "") for item in PricingStrategy],
        **translation_context,
    )

    def set_account_pricing_strategy(self, value):
        self.account_pricing_strategy = value
        bpy.context.preferences.use_preferences_save = True

    # 环境配置
    use_dev_environment: bpy.props.BoolProperty(
        name="Use Development Environment",
        default=False,
        **translation_context,
    )

    dev_api_base_url: bpy.props.StringProperty(
        name="Dev API Base URL",
        default="",
        **translation_context,
    )

    dev_login_url: bpy.props.StringProperty(
        name="Dev Login URL",
        default="",
        **translation_context,
    )

    dev_token: bpy.props.StringProperty(
        name="Dev Token",
        default="",
        **translation_context,
    )

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
        self.draw_service(layout.box())

    def draw_online_update(self, layout):
        UpdateService.draw_update_info(layout)

    def draw_account(self, layout):
        layout.prop(self, "account_auth_mode", text="Operating Mode")
        if not self.is_api_mode:
            layout.prop(self, "account_pricing_strategy", text="Pricing Strategy")

    def draw_dev(self, layout):
        # 环境配置
        column = layout.column()
        column.label(text="Environment Settings")
        column.prop(self, "use_dev_environment")

        if self.use_dev_environment:
            column.prop(self, "init_privacy")
            column.prop(self, "dev_api_base_url")
            column.prop(self, "dev_login_url")
            column.prop(self, "dev_token")

    def draw_service(self, layout):
        from ..studio.account import Account

        layout.label(text="Service")
        self.draw_account(layout)

        if self.is_backup_mode:
            account = Account.get_instance()
            if account.is_logged_in():
                layout.label(text=iface("Logged in") + account.nickname)
                layout.label(text=iface("Credits : %s") % str(account.credits))
                layout.operator("bas.logout_account_auth")
            elif account.is_waiting_for_login():
                layout.label(text="Waiting for login...")
            else:
                layout.label(text="Not logged in")
                layout.operator("bas.login_account_auth")
        else:
            self.draw_api(layout)


def register():
    bpy.utils.register_class(BlenderAIStudioPref)


def unregister():
    bpy.utils.unregister_class(BlenderAIStudioPref)
