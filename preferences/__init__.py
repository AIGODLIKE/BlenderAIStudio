import bpy

from .. import __package__ as base_name


class BlenderAIStudioPref(bpy.types.AddonPreferences):
    bl_idname = base_name


    def draw(self, context):
        layout = self.layout
        layout.label(text="Blender AI Studio Preferences")


def register():
    bpy.utils.register_class(BlenderAIStudioPref)


def unregister():
    bpy.utils.unregister_class(BlenderAIStudioPref)
