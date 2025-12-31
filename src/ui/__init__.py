import bpy

from .menu import SelectMaskMenu, RenderButtonMenu
from .panel import AIStudioImagePanel, AIStudioHistoryPanel
from ..icons import previews_icons

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
    icon = previews_icons.get("ai")
    icon_id = 0
    if icon:
        icon_id = icon.icon_id
    col.operator(AIStudioEntry.bl_idname, text="", icon_value=icon_id)


def register():
    register_classes()
    bpy.types.VIEW3D_HT_header.append(draw_ai_studio_button)


def unregister():
    bpy.types.VIEW3D_HT_header.remove(draw_ai_studio_button)
    unregister_classes()
