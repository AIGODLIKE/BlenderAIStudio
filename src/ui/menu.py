import bpy


class SelectMaskMenu(bpy.types.Menu):
    bl_idname = "BAS_MT_select_mask_menu"
    bl_label = "Select Mask Menu"

    @classmethod
    def poll(cls, context):
        space_data = context.space_data
        return space_data and space_data.image is not None

    def draw(self, context):
        layout = self.layout
        column = layout.column(align=True)
        oii = context.scene.blender_ai_studio_property
        for index, m in enumerate(oii.mask_images):
            if m.image and m.image.preview:
                box = column.column(align=True)
                box.template_icon(m.image.preview.icon_id, scale=6)
                row = box.row(align=True)
                ops = row.operator("bas.select_mask", text=m.image.name, icon="RESTRICT_SELECT_OFF", translate=False)
                ops.index = index
                ops.remove = False
                ops = row.operator("bas.select_mask", text="", icon="TRASH")
                ops.index = index
                ops.remove = True
        if len(oii.mask_images) == 0:
            column.label(text="No mask available, please draw")
