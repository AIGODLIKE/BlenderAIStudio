from __future__ import annotations

import bpy


class ImageItem(bpy.types.PropertyGroup):
    image: bpy.props.PointerProperty(type=bpy.types.Image, name="图片")


class ImageProperty(bpy.types.PropertyGroup):
    """
    图片属性
    """
    origin_image: bpy.props.PointerProperty(type=bpy.types.Image, name="原图图片")
    is_mask_image: bpy.props.BoolProperty(name="Is Mask Image", default=False)


class SceneProperty(bpy.types.PropertyGroup):
    """
    生成的属性
    """
    origin_image: bpy.props.PointerProperty(type=bpy.types.Image, name="原图图片")
    generated_image: bpy.props.PointerProperty(type=bpy.types.Image, name="生成的图片")
    reference_images: bpy.props.CollectionProperty(type=ImageItem, name="多张参考图", description="最大14张输入图片")
    mask_images: bpy.props.CollectionProperty(type=ImageItem, name="编辑的图片")

    hide_reference: bpy.props.BoolProperty(name="Hide Reference Images", default=True)
    mask_index: bpy.props.IntProperty(name="Mask Image Index", default=0)

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

    history: bpy.props.CollectionProperty(type=SceneProperty)

    @property
    def all_references_images(self) -> list[bpy.types.Image]:
        return [i.image for i in self.reference_images if i.image]

    @property
    def active_mask(self) -> bpy.types.Image | None:
        """
        获取当前使用的蒙版图片
        """
        index = self.mask_index
        if 0 <= index <= len(self.mask_images) - 1:
            return self.mask_images[index].image
        return None

    def draw_reference_images(self, context, layout: bpy.types.UILayout):
        box = layout.box()

        # 参考图头
        row = box.row()
        row.alignment = "EXPAND"
        rr = row.row()
        rr.alignment = "LEFT"
        text = bpy.app.translations.pgettext_iface("Reference Images")
        rl = len(self.reference_images)
        alert = rl > 12
        count = f" ({rl})" if rl else ""
        rr.alert = alert
        rr.prop(self, "hide_reference", text=f"{text}{count}",
                icon="RIGHTARROW" if self.hide_reference else "DOWNARROW_HLT",
                emboss=False,
                )
        if alert:
            rr.label(text="", icon="ERROR")
        rr = row.row()
        rr.alignment = "RIGHT"
        rr.operator("bas.select_reference_image_by_image", text="", icon="IMAGE_REFERENCE", emboss=False)
        rr.operator("bas.select_reference_image_by_file", text="", icon="ADD", emboss=False)
        if self.hide_reference:
            return

        """
        # row.template_ID(item, "icons", open="icons.open")
        # row.template_ID_preview(item, "icons", hide_buttons=True)
        # row.template_preview(item.icons)
        # row.template_icon_view(item, "icons")
        # row.template_image(item, "icons")
        # column.label(text=f"{context.region.width}")
        ly.template_search_preview(self, "reference_image", bpy.data, "images")
        for i in bpy.context.scene.blender_ai_studio_property.mask_images:print(i)
        """

        column = box.column()
        is_small_width = context.region.width < 200
        if alert:
            col = column.column()
            col.alert = True
            col.label(text="Too many reference images, please remove some")
            col.label(text="Up to 12 images can be selected")
        # column.prop(self, "scale")
        for i, item in enumerate(self.reference_images):
            if item.image:
                if is_small_width:
                    ly = column.column(align=True)
                else:
                    ly = column.row(align=True)
                ly.box().template_icon(item.image.preview.icon_id, scale=5)

                if is_small_width:
                    lay = ly.row(align=True)
                    # lay.scale_x = self.scale
                else:
                    lay = ly.column(align=True)
                    # lay.scale_y = self.scale
                lay.operator("bas.remove_reference_image", text="", icon="X",
                             # emboss=False
                             ).index = i
                lay.operator("bas.replace_reference_image", text="", icon="FILE_REFRESH",
                             # emboss=False
                             ).index = i
        if rl == 0:
            box.label(text="Click top right ops to reference")

    scale: bpy.props.FloatProperty(default=2.75)

    def draw_history(self, layout: bpy.types.UILayout):
        ...


class_list = [
    ImageItem,
    SceneProperty,
    ImageProperty,
]
register_class, unregister_class = bpy.utils.register_classes_factory(class_list)


def register():
    register_class()
    bpy.types.Scene.blender_ai_studio_property = bpy.props.PointerProperty(type=SceneProperty)
    bpy.types.Image.blender_ai_studio_property = bpy.props.PointerProperty(type=ImageProperty)
    bpy.types.Text.blender_ai_studio_prompt_hash = bpy.props.StringProperty()


def unregister():
    del bpy.types.Scene.blender_ai_studio_property
    del bpy.types.Image.blender_ai_studio_property
    del bpy.types.Text.blender_ai_studio_prompt_hash
    unregister_class()
