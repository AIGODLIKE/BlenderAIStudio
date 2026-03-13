import bpy

from ..i18n import PROP_TCTX

translation_context = {}

if bpy.app.version >= (4, 0, 0):
    translation_context["translation_context"] = PROP_TCTX


class Debug:
    use_dev_ui: bpy.props.BoolProperty(
        name="Use Development UI",
        default=False,
        **translation_context,
    )
    # 环境配置
    use_dev_environment: bpy.props.BoolProperty(
        name="Use Development Environment",
        default=False,
        **translation_context,
    )
    use_debug_mode: bpy.props.BoolProperty(
        name="Use Development Mode",
        default=True,
        **translation_context,
    )

    dev_api_base_url: bpy.props.StringProperty(
        name="Dev API Base URL",
        default="",
        subtype="PASSWORD",
        **translation_context,
    )

    dev_login_url: bpy.props.StringProperty(
        name="Dev Login URL",
        default="",
        subtype="PASSWORD",
        **translation_context,
    )

    dev_token: bpy.props.StringProperty(
        name="Dev Token",
        default="",
        subtype="PASSWORD",
        **translation_context,
    )

    enable_experimental_features: bpy.props.BoolProperty(
        name="Experimental Features",
        description="Enable experimental features that may be unstable, Restart if enabled",
        default=False,
        **translation_context,
    )

    def draw_dev(self, layout):
        # 环境配置
        column = layout.column()
        column.operator("bas.upload_error_report", icon="URL")
        column.label(text="Environment Settings")
        column.prop(self, "init_privacy")
        column.prop(self, "use_debug_mode")
        column.prop(self, "use_dev_ui")
        column.prop(self, "use_dev_environment")

        if self.use_dev_environment:
            column.prop(self, "dev_api_base_url")
            column.prop(self, "dev_login_url")
            column.prop(self, "dev_token")
