import bpy
from .ui import AIStudioPanel


clss = [
    AIStudioPanel,
]

reg, unreg = bpy.utils.register_classes_factory(clss)


def register():
    reg()


def unregister():
    unreg()
