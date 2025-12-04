import bpy

from .. import __package__ as base_name


class BlenderAIStudioPref(bpy.types.AddonPreferences):
    bl_idname = base_name
    nano_banana_api: bpy.props.StringProperty(
        name="Nano Banana API Key",
        subtype="PASSWORD",
    )

    def draw(self, context):
        layout = self.layout
        layout.label(text="Blender AI Studio Preferences")
        layout.prop(self, "nano_banana_api")

        if self.nano_banana_api == "":
            layout.label(text="Please input your API Key")


def get_pref() -> BlenderAIStudioPref:
    return bpy.context.preferences.addons[base_name].preferences


def register():
    bpy.utils.register_class(BlenderAIStudioPref)


def unregister():
    bpy.utils.unregister_class(BlenderAIStudioPref)
