from __future__ import annotations

import bpy


class ImageItem(bpy.types.PropertyGroup):
    image: bpy.props.PointerProperty(type=bpy.types.Image, name="图片")


class GenerateProperty(bpy.types.PropertyGroup):
    """
    生成的属性
    """
    origin_image: bpy.props.PointerProperty(type=bpy.types.Image, name="原图图片")
    mask_image: bpy.props.PointerProperty(type=bpy.types.Image, name="编辑的图片")
    reference_images: bpy.props.CollectionProperty(type=ImageItem, name="多张参考图")
    reference_image: bpy.props.PointerProperty(type=ImageItem, name="单张参考图")
    hide_reference_images: bpy.props.BoolProperty(name="Hide Reference Images", default=True)

    prompt: bpy.props.StringProperty(
        name="Prompt",
        maxlen=1000,
    )
    resolution: bpy.props.EnumProperty(
        name="Out Resolution",
        items=[
            ("INPUT", "Input Size", "Keep original resolution"),
            ("1k", "1k(1024x1024)", "1k resolution"),
            ("2k", "2k(2048x2048)", "2k resolution"),
            ("4k", "4k(4096x4096)", "4k resolution"),
        ],
        default="INPUT",
    )

    history: bpy.props.CollectionProperty(type=GenerateProperty)

    @property
    def all_references_images(self) -> list[bpy.types.Image]:
        return [i.image for i in self.reference_images if i.image]

    def draw_reference_images(self, context, layout: bpy.types.UILayout):
        box = layout.box()

        # 参考图头
        row = box.row()
        row.alignment = "EXPAND"
        rr = row.row()
        rr.alignment = "LEFT"
        text = bpy.app.translations.pgettext_iface("Reference Images")
        rl = len(self.reference_images)
        count = f" ({rl})" if rl else ""
        rr.prop(self, "hide_reference_images", text=f"{text}{count}",
                icon="RIGHTARROW" if self.hide_reference_images else "DOWNARROW_HLT",
                emboss=False,
                )
        row.separator()
        rr = row.row()
        rr.alignment = "RIGHT"
        rr.operator("bas.select_reference_image_by_image", text="", icon="IMAGE_REFERENCE", emboss=False)
        rr.operator("bas.select_reference_image_by_file", text="", icon="ADD", emboss=False)
        if self.hide_reference_images:
            return

        column = box.column()
        """
        # row.template_ID(item, "image", open="image.open")
        # row.template_ID_preview(item, "image", hide_buttons=True)
        # row.template_preview(item.image)
        # row.template_icon_view(item, "image")
        # row.template_image(item, "image")
        # column.label(text=f"{context.region.width}")
        ly.template_search_preview(self, "reference_image", bpy.data, "images")
        """

        is_small_width = context.region.width < 300
        for i, item in enumerate(self.reference_images):
            if item.image:
                if is_small_width:
                    ly = column.column(align=True)
                else:
                    ly = column.row(align=True)
                ly.template_icon(item.image.preview.icon_id, scale=5)
                col = ly.column(align=True)
                if not is_small_width:
                    col.label(text=item.image.name)
                col.operator("bas.remove_reference_image", text="", icon="X", emboss=False).index = i
        if rl == 0:
            box.label(text="Click top right ops to reference")

    def draw_history(self, layout: bpy.types.UILayout):
        ...


class_list = [
    ImageItem,
    GenerateProperty,
]
register_class, unregister_class = bpy.utils.register_classes_factory(class_list)


def register():
    register_class()
    bpy.types.Scene.blender_ai_studio_property = bpy.props.PointerProperty(type=GenerateProperty)
    bpy.types.Image.blender_ai_studio_property = bpy.props.PointerProperty(type=GenerateProperty)


def unregister():
    del bpy.types.Scene.blender_ai_studio_property
    del bpy.types.Image.blender_ai_studio_property
    unregister_class()
