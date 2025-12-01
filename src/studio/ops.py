import bpy
from ..i18n import OPS_TCTX


class AIStudioEntry(bpy.types.Operator):
    bl_idname = "bas.open_ai_studio"
    bl_description = "Open AI Studio"
    bl_translation_context = OPS_TCTX
    bl_label = "AI Studio Entry"

    def execute(self, context):
        # Open AI Studio
        print("Opening AI Studio")
        return {"FINISHED"}


clss = [
    AIStudioEntry,
]

reg, unreg = bpy.utils.register_classes_factory(clss)


def register():
    reg()


def unregister():
    unreg()
