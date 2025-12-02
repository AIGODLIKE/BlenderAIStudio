import bpy

from .studio import AIStudio
from ..i18n import OPS_TCTX


class AIStudioEntry(bpy.types.Operator):
    bl_idname = "bas.open_ai_studio"
    bl_description = "Open AI Studio"
    bl_translation_context = OPS_TCTX
    bl_label = "AI Studio Entry"

    def invoke(self, context, event):
        self.area = bpy.context.area
        self.app = AIStudio()
        self.app.draw_call_add(self.app.handler_draw)

        self._timer = context.window_manager.event_timer_add(1 / 60, window=context.window)
        context.window_manager.modal_handler_add(self)

        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if context.area != self.area:
            return {"PASS_THROUGH"}
        context.area.tag_redraw()
        if self.app.is_closed():
            return {"FINISHED"}
        self.app.push_event(event)
        if self.app.should_pass_event():
            return {"PASS_THROUGH"}
        if self.app.should_exit():
            self.app.shutdown()
        return {"RUNNING_MODAL"}


class EditImage(bpy.types.Operator):
    bl_idname = "bas.edit_image"
    bl_description = "Edit Image"
    bl_translation_context = OPS_TCTX
    bl_label = "Edit Image"

    @classmethod
    def poll(cls, context):
        space = context.space_data
        return getattr(space, "image", None)

    def execute(self, context):
        space = context.space_data
        image = getattr(space, "image")
        print(self.bl_idname, image)
        return {"FINISHED"}


class ApplyEditImage(bpy.types.Operator):
    bl_idname = "bas.apply_edit_image"
    bl_description = "Apply Edit Image"
    bl_translation_context = OPS_TCTX
    bl_label = "Apply Edit Image"

    @classmethod
    def poll(cls, context):
        space = context.space_data
        return getattr(space, "image", None)

    def execute(self, context):
        image = getattr(context, "image")
        print(self.bl_idname, image)
        return {"FINISHED"}


class GenerateImage(bpy.types.Operator):
    bl_idname = "bas.generate_image"
    bl_description = "Generate Image"
    bl_translation_context = OPS_TCTX
    bl_label = "Generate Image"

    def execute(self, context):
        return {"FINISHED"}


clss = [
    AIStudioEntry,
    EditImage,
    ApplyEditImage,
    GenerateImage,
]

reg, unreg = bpy.utils.register_classes_factory(clss)


def register():
    reg()


def unregister():
    unreg()
