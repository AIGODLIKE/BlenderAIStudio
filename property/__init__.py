import bpy


class GenerateHistory(bpy.types.PropertyGroup):
    ...


def register():
    bpy.utils.register_class(GenerateHistory)
    bpy.types.Scene.generate_history = PointerProperty(type=GenerateHistory)


def unregister():
    del bpy.types.Scene.generate_history
    bpy.utils.unregister_class(GenerateHistory)
