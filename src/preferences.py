import bpy

from .. import __package__ as base_name


class BlenderAIStudioPref(bpy.types.AddonPreferences):
    bl_idname = base_name
    api: bpy.props.StringProperty(
        name="API Key",
        subtype="PASSWORD",
    )

    def draw(self, context):
        layout = self.layout
        layout.label(text="Blender AI Studio Preferences")
        layout.prop(self, "api")

        if self.api == "":
            layout.label(text="Please input your API Key")


def register():
    bpy.utils.register_class(BlenderAIStudioPref)


def unregister():
    bpy.utils.unregister_class(BlenderAIStudioPref)
