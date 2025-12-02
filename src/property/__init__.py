import bpy


class GenerateHistory(bpy.types.PropertyGroup):
    """
    生成历史记录
    """
    origin: bpy.props.PointerProperty(type=bpy.types.Image)
    edit_image: bpy.props.PointerProperty(type=bpy.types.Image)
    generate_image: bpy.props.PointerProperty(type=bpy.types.Image)
    reference_image: bpy.props.PointerProperty(type=bpy.types.Image)
    description: bpy.props.StringProperty(name="描述")


class GenerateProperty(bpy.types.PropertyGroup):
    mode: bpy.props.EnumProperty(name="生成模式", items=[
        ("ORIGIN", "原图", "原图"),
        ("EDIT", "编辑", "编辑"),
        ("GENERATE", "生成", "生成"),
        ("REFERENCE", "参考", "参考"),
    ])


class ImageProperty(bpy.types.PropertyGroup):
    is_edit_image: bpy.props.BoolProperty(name="是否是编辑图片")
    is_generate_image: bpy.props.BoolProperty(name="是否是生成图片")


def register():
    bpy.utils.register_class(GenerateHistory)
    bpy.utils.register_class(ImageProperty)
    bpy.utils.register_class(GenerateProperty)

    bpy.types.Image.blender_ai_studio_image_property = bpy.props.PointerProperty(type=ImageProperty)
    bpy.types.Scene.blender_ai_studio = bpy.props.PointerProperty(type=GenerateProperty)
    bpy.types.Scene.blender_ai_studio_generate_history = bpy.props.CollectionProperty(type=GenerateHistory)


def unregister():
    del bpy.types.Scene.blender_ai_studio_generate_history
    del bpy.types.Scene.blender_ai_studio
    del bpy.types.Image.blender_ai_studio_image_property
    bpy.utils.unregister_class(GenerateHistory)
    bpy.utils.unregister_class(ImageProperty)
    bpy.utils.unregister_class(GenerateProperty)
