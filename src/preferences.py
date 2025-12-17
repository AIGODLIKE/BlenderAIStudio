import bpy
from .i18n import PROP_TCTX
from .. import __package__ as base_name

translation_context = {}
if bpy.app.version >= (4, 0, 0):
    translation_context["translation_context"] = PROP_TCTX


class BlenderAIStudioPref(bpy.types.AddonPreferences):
    bl_idname = base_name
    ui_pre_scale: bpy.props.FloatProperty(
        name="UI Pre Scale Factor",
        default=1,
        min=0.1,
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
    nano_banana_api: bpy.props.StringProperty(
        name="Nano Banana API Key",
        subtype="PASSWORD",
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "ui_pre_scale")
        layout.prop(self, "ui_offset")
        layout.label(text="Blender AI Studio Preferences")
        layout.prop(self, "nano_banana_api")

        if self.nano_banana_api == "":
            layout.label(text="Please input your API Key")

    def set_ui_offset(self, value):
        self.ui_offset = value
        bpy.context.preferences.use_preferences_save = True


def get_pref() -> BlenderAIStudioPref:
    return bpy.context.preferences.addons[base_name].preferences


def register():
    bpy.utils.register_class(BlenderAIStudioPref)


def unregister():
    bpy.utils.unregister_class(BlenderAIStudioPref)
