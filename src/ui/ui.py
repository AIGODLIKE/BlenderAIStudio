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
        space_data = context.space_data
        image = space_data.image
        ai = context.scene.blender_ai_studio_property

        layout = self.layout

        self.draw_image_info(context, layout)

        box = layout.box()
        box.label(text="Prompt", icon='TEXT')
        box.prop(ai, "prompt", text="")

        ai.draw_reference_images(context, layout)

        layout.operator("bas.edit_image")
        layout.operator("bas.apply_edit_image")
        layout.operator("bas.generate_image")

    def draw_image_info(self, context, layout: bpy.types.UILayout):
        image = context.space_data.image
        ai = context.scene.blender_ai_studio_property
        w, h = image.size[:]

        layout.column(heading="Image Info")
        box = layout.box()
        box.label(text=f"{image.name}")
        box.label(text=f"{bpy.app.translations.pgettext_iface('Image size')}(px): {w} x {h}")
        split = box.split(factor=0.2)
        split.label(text="Out Resolution")
        split.prop(ai, "resolution", text="")


class AIStudioHistoryPanel(bpy.types.Panel):
    bl_idname = "SDN_PT_BLENDER_AI_STUDIO_PT_History"
    bl_label = "History"
    bl_description = "生成历史"
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "AIStudio"

    # bl_options = {"HIDE_HEADER", "INSTANCED"}

    @classmethod
    def poll(cls, context):
        space_data = context.space_data
        return space_data and space_data.image is not None

    def draw(self, context):
        layout = self.layout

        space_data = context.space_data
        image = space_data.image
        layout.label(text="History")
