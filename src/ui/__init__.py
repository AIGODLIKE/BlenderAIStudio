import bpy

from .menu import SelectMaskMenu, RenderButtonMenu
from .panel import AIStudioImagePanel, AIStudioHistoryPanel
from ..icons import get_icon

clss = [
    AIStudioImagePanel,
    AIStudioHistoryPanel,

    SelectMaskMenu,
    RenderButtonMenu,
]

register_classes, unregister_classes = bpy.utils.register_classes_factory(clss)


def draw_ai_studio_button(self, context):
    from ..studio.ops import AIStudioEntry

    layout = self.layout
    col = layout.column()
    col.operator(AIStudioEntry.bl_idname, text="", icon_value=get_icon("ai"))


def draw_ai_studio_edit_button(self, context):
    from ..ops.entry_edit_image import EntryEditImage

    layout = self.layout
    col = layout.column()
    col.operator(EntryEditImage.bl_idname, text="", icon_value=get_icon("ai"))


def register():
    register_classes()
    bpy.types.VIEW3D_HT_header.append(draw_ai_studio_button)
    bpy.types.IMAGE_HT_header.append(draw_ai_studio_edit_button)


def unregister():
    bpy.types.VIEW3D_HT_header.remove(draw_ai_studio_button)
    bpy.types.IMAGE_HT_header.remove(draw_ai_studio_edit_button)
    unregister_classes()
