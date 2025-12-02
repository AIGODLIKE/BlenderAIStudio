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
        origin = getattr(space, "image")
        origin.use_fake_user = True
        edit_image = origin.copy()

        edit_image.name = f"{origin.name}_edit"
        edit_image.use_fake_user = True
        aip = edit_image.blender_ai_studio_image_property
        aip.is_edit_image = True
        print(self.bl_idname, origin)

        space.image = edit_image
        space.ui_mode = "PAINT"
        bpy.ops.brush.asset_activate(
            asset_library_type='ESSENTIALS',
            asset_library_identifier="",
            relative_asset_identifier="brushes\\essentials_brushes-mesh_texture.blend\\Brush\\Erase Hard")
        return {"FINISHED"}


class ApplyEditImage(bpy.types.Operator):
    bl_idname = "bas.apply_edit_image"
    bl_description = "Apply Edit Image"
    bl_translation_context = OPS_TCTX
    bl_label = "Apply Edit Image"

    @classmethod
    def poll(cls, context):
        space = context.space_data
        image = getattr(space, "image", None)
        return image and image.blender_ai_studio_image_property.is_edit_image

    def execute(self, context):
        space = context.space_data
        origin = getattr(space, "image")
        print(self.bl_idname, origin)
        origin.use_fake_user = True
        origin.save()

        edit_image = origin.copy()
        edit_image.use_fake_user = True
        edit_image.name = f"{origin.name}_apply"
        aip = edit_image.blender_ai_studio_image_property
        aip.is_edit_image = False
        space.image = edit_image
        space.ui_mode = "VIEW"
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
