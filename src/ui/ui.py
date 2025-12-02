import bpy
from ..i18n import PANEL_TCTX
from ..studio import AIStudioEntry


class AIStudioPanel(bpy.types.Panel):
    bl_idname = "SDN_PT_BLENDER_AI_STUDIO"
    bl_translation_context = PANEL_TCTX
    bl_label = "Blender AI Studio"
    bl_description = ""
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "AIStudio"

    def draw(self, context):
        layout = self.layout
        layout.label(text="Blender AI Studio")
        layout.operator(AIStudioEntry.bl_idname)


class AIStudioImagePanel(bpy.types.Panel):
    bl_idname = "SDN_PT_BLENDER_AI_STUDIO_PT_Image"
    bl_translation_context = PANEL_TCTX
    bl_label = "Blender AI Studio"
    bl_description = ""
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "AIStudio"

    @classmethod
    def poll(cls, context):
        space_data = context.space_data
        return space_data and space_data.image is not None

    def draw(self, context):
        layout = self.layout
        layout.label(text="Blender AI Studio")
        layout.operator(AIStudioEntry.bl_idname)
