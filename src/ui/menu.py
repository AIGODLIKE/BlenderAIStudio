import bpy


class SelectMaskMenu(bpy.types.Menu):
    bl_idname = "BAS_MT_select_mask_menu"
    bl_label = "Select Mask Menu"

    @classmethod
    def poll(cls, context):
        space_data = context.space_data
        return space_data and space_data.image is not None

    def draw(self, context):
        from ..studio.ops import SelectMask
        SelectMask.draw_select_mask(context, self.layout)
