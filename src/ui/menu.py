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


class RenderButtonMenu(bpy.types.Menu):
    bl_idname = "BAS_MT_render_button_menu"
    bl_label = "Render Button Menu"

    @classmethod
    def poll(cls, context):
        space_data = context.space_data
        return space_data and space_data.image is not None

    def draw(self, context):
        column = self.layout.column(align=True)
        column.scale_y = 1.5
        column.operator("bas.rerender_image", icon="RENDER_STILL")
        column.operator("bas.finalize_composite", icon="RENDERLAYERS")
