import bpy
from .ui import AIStudioPanel, AIStudioImagePanel

clss = [
    AIStudioPanel,
    AIStudioImagePanel,
]

reg, unreg = bpy.utils.register_classes_factory(clss)


def register():
    reg()


def unregister():
    unreg()
