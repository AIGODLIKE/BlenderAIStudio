import bpy

from .ui import AIStudioPanel, AIStudioImagePanel, AIStudioHistoryPanel

clss = [
    AIStudioPanel,
    AIStudioImagePanel,
    AIStudioHistoryPanel,
]

reg, unreg = bpy.utils.register_classes_factory(clss)


def register():
    reg()


def unregister():
    unreg()
