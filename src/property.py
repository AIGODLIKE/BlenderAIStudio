from __future__ import annotations

import bpy


class ImageItem(bpy.types.PropertyGroup):
    image: bpy.props.PointerProperty(type=bpy.types.Image, name="图片")


class GenerateProperty(bpy.types.PropertyGroup):
    """
    生成的属性
    """
    origin_image: bpy.props.PointerProperty(type=bpy.types.Image, name="原图图片")
    edit_image: bpy.props.PointerProperty(type=bpy.types.Image, name="编辑的图片")
    generate_image: bpy.props.PointerProperty(type=bpy.types.Image, name="生成图片")
    reference_images: bpy.props.CollectionProperty(type=ImageItem, name="多张参考图")
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

    def draw_reference_images(self, layout: bpy.types.UILayout):
        box = layout.box()
        box.label(text="Reference Images")
        for i, item in enumerate(self.reference_images):
            box.template_ID(item, "image", open="image.open")
            box.operator("bas.remove_reference_image", text="", icon="X", depress=True).index = i
            box.separator()
        box.operator("bas.add_reference_image", text="", icon="ADD")

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
