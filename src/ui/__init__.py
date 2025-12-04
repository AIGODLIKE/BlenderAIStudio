import bpy

from .menu import SelectMaskMenu
from .panel import AIStudioPanel, AIStudioImagePanel, AIStudioHistoryPanel

clss = [
    AIStudioPanel,
    AIStudioImagePanel,
    AIStudioHistoryPanel,

    SelectMaskMenu,
]

register_classes, unregister_classes = bpy.utils.register_classes_factory(clss)


def register():
    register_classes()


def unregister():
    unregister_classes()
