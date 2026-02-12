import bpy

from ..i18n.translations.zh_HANS import OPS_TCTX
from ..ui import AIStudioImagePanel


class EntryEditImage(bpy.types.Operator):
    bl_idname = "bas.entry_edit_image"
    bl_label = "Entry Edit Image"
    bl_translation_context = OPS_TCTX

    @classmethod
    def poll(cls, context):
        space_data = context.space_data
        return space_data and space_data.image is not None

    def execute(self, context):
        if space_date := context.space_data:
            space_date.show_region_ui = True
        for region in context.area.regions:
            if region.type == "UI":
                region.active_panel_category = AIStudioImagePanel.bl_category
        return {"FINISHED"}
