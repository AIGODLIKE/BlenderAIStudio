import json
from pathlib import Path
from uuid import uuid4

import bpy
from bpy_extras.io_utils import ImportHelper, ExportHelper

from ..i18n import OPS_TCTX
from ..utils import (get_text_generic_keymap, get_text_window, get_pref, save_image_to_temp_folder, png_name_suffix,
                     load_image,
                     )


class AIStudioEntry(bpy.types.Operator):
    bl_idname = "bas.open_ai_studio"
    bl_description = "Open AI Studio"
    bl_translation_context = OPS_TCTX
    bl_label = "AI Studio Entry"
    entry_pool: dict = {}

    def invoke(self, context, event):
        from .studio import AIStudio
        self.area = bpy.context.area
        if self.area.as_pointer() in self.entry_pool:
            self.report({'ERROR'}, "AI Studio is already opened")
            return {'FINISHED'}
        self.app = AIStudio()
        self.app.draw_call_add(self.app.handler_draw)
        self.entry_pool[self.area.as_pointer()] = self.app

        self._timer = context.window_manager.event_timer_add(1 / 60, window=context.window)
        context.window_manager.modal_handler_add(self)

        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        if context.area:
            if context.area != self.area:
                return {"PASS_THROUGH"}
            context.area.tag_redraw()
        else:
            self.app.queue_shoutdown()
        if self.app.should_exit():
            self.app.shutdown()
        if self.app.is_closed():
            print("AI Studio closed")
            self.entry_pool.pop(self.area.as_pointer(), None)
            return {"FINISHED"}
        self.app.push_event(event)
        if self.app.should_pass_event():
            return {"PASS_THROUGH"}
        return {"RUNNING_MODAL"}


class FileCallbackRegistry:
    """管理文件选择回调的注册表"""

    _registry = {}

    @classmethod
    def register_callback(cls, callback, *args, **kwargs):
        """注册回调并返回唯一ID"""
        callback_id = str(uuid4())
        cls._registry[callback_id] = {"callback": callback, "args": args, "kwargs": kwargs}
        return callback_id

    @classmethod
    def execute_callback(cls, callback_id, filepath):
        """执行注册的回调"""
        if callback_id in cls._registry:
            data = cls._registry.pop(callback_id)  # 执行后移除
            callback = data["callback"]
            args = data["args"]
            kwargs = data["kwargs"]
            return callback(filepath, *args, **kwargs)
        return None


class FileImporter(bpy.types.Operator, ImportHelper):
    bl_idname = "bas.file_importer"
    bl_label = "Import File"

    filter_glob: bpy.props.StringProperty(default="*.png;*.jpg;*.jpeg;*.bmp;*.tiff;", options={"HIDDEN"})
    filepath: bpy.props.StringProperty(subtype="FILE_PATH")
    callback_id: bpy.props.StringProperty()

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event):
        bpy.context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        img_path = Path(self.filepath).as_posix()
        FileCallbackRegistry.execute_callback(self.callback_id, img_path)
        return {"FINISHED"}


class FileExporter(bpy.types.Operator, ExportHelper):
    bl_idname = "bas.file_exporter"
    bl_label = "Export File"

    filename_ext = ".png"

    filter_glob: bpy.props.StringProperty(default="*.png;*.jpg;*.jpeg;", options={"HIDDEN"})
    filepath: bpy.props.StringProperty(subtype="FILE_PATH")
    callback_id: bpy.props.StringProperty()

    def execute(self, context):
        img_path = Path(self.filepath).as_posix()
        FileCallbackRegistry.execute_callback(self.callback_id, img_path)
        return {"FINISHED"}


class DrawImageMask(bpy.types.Operator):
    bl_idname = "bas.draw_mask"
    bl_label = "Draw Mask"
    bl_options = {"REGISTER"}
    bl_translation_context = OPS_TCTX
    bl_description = "Mask"
    run_count: bpy.props.IntProperty(default=0)

    is_edit: bpy.props.BoolProperty(default=False)

    @classmethod
    def poll(cls, context):
        space = context.space_data
        image = getattr(space, "image", None)
        return image and not image.blender_ai_studio_property.is_mask_image

    def invoke(self, context, event):
        bpy.ops.ed.undo_push(message="Push Undo")
        space = context.space_data
        print(self.bl_idname)

        image = getattr(space, "image")
        image.use_fake_user = True
        scene_prop = context.scene.blender_ai_studio_property

        name = png_name_suffix(image.name, "_mask")

        if self.is_edit:
            mask_image = getattr(context, "image", None)
        else:
            mask_image = image.copy()
            mask_image.use_fake_user = True
            try:
                if not mask_image.packed_file:
                    mask_image.pack()
            except RuntimeError as e:
                print("pack error", e)
            mask_image.filepath = ""
            mask_image.name = name

            mi = scene_prop.mask_images.add()  # 新创建一个mask图
            mi.name = name
            mi.image = mask_image

            aip = mask_image.blender_ai_studio_property
            aip.is_mask_image = True
            aip.origin_image = image
        if mask_image is None:
            self.report({"ERROR"}, "Can't create mask image")
            return {"CANCELLED"}
        space.image = mask_image
        space.ui_mode = "PAINT"

        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    def modal(self, context, event):
        from bl_ui.properties_paint_common import UnifiedPaintPanel
        space = context.space_data
        if space.ui_mode == "PAINT":
            space.uv_editor.show_uv = False
        if paint_settings := getattr(UnifiedPaintPanel.paint_settings(context), "unified_paint_settings", None):
            bpy.ops.brush.asset_activate(
                "EXEC_DEFAULT",
                False,
                asset_library_type='ESSENTIALS',
                asset_library_identifier="",
                relative_asset_identifier=r"brushes\\essentials_brushes-mesh_texture.blend\\Brush\\Paint Hard Pressure")
            paint_settings.size = 4
            paint_settings.color = [1, 0, 0]
            bpy.ops.ed.undo_push(message="Push Undo")
            return {"FINISHED"}

        if self.run_count > 20:  # 最多等待20次
            return {'CANCELLED'}
        self.run_count += 1
        return {"RUNNING_MODAL"}


class ApplyImageMask(bpy.types.Operator):
    bl_idname = "bas.apply_image_mask"
    bl_translation_context = OPS_TCTX
    bl_label = "Apply Image Mask"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        space = context.space_data
        image = getattr(space, "image", None)
        return image and image.blender_ai_studio_property.origin_image

    def execute(self, context):
        space = context.space_data
        image = getattr(space, "image")
        print(self.bl_idname, image)
        bpy.ops.image.save("EXEC_DEFAULT", False)
        image.preview_ensure()
        image.use_fake_user = True
        if image.preview:
            image.preview.reload()

        ai = image.blender_ai_studio_property
        oii = context.scene.blender_ai_studio_property

        space.image = ai.origin_image
        space.ui_mode = "VIEW"
        for index, m in enumerate(oii.mask_images):
            if m.image == image:
                oii.mask_index = index
                continue
        return {"FINISHED"}


class SelectMask(bpy.types.Operator):
    bl_idname = "bas.select_mask"
    bl_translation_context = OPS_TCTX
    bl_label = "Select Mask"
    bl_options = {"REGISTER"}
    index: bpy.props.IntProperty()
    remove: bpy.props.BoolProperty(default=False)

    @classmethod
    def description(cls, context, properties):
        if properties.remove:
            return "Remove Mask"
        if properties.index == -1:
            return "Not using mask"
        return cls.bl_label

    @classmethod
    def poll(cls, context):
        space = context.space_data
        image = getattr(space, "image", None)
        return image

    def invoke(self, context, event):
        return context.window_manager.invoke_popup(self)

    def execute(self, context):
        space = context.space_data
        image = getattr(space, "image", None)
        oii = context.scene.blender_ai_studio_property
        print(self.bl_idname, self.index, image)

        if self.remove:
            ri = oii.mask_images[self.index].image
            if image and ri == image:
                oi = ri.blender_ai_studio_property.origin_image
                if oi:
                    setattr(context.space_data, "image", oi)
            oii.mask_images.remove(self.index)
        else:
            oii.mask_index = self.index
            if space.ui_mode == "PAINT":
                space.image = oii.active_mask
        return {"FINISHED"}

    def draw(self, context):
        layout = self.layout
        self.draw_select_mask(context, layout)

    @staticmethod
    def draw_select_mask(context, layout, use_box=False):
        column = layout.column(align=True)
        column.label(text="Mask History")
        column.operator_context = "EXEC_DEFAULT"
        oii = context.scene.blender_ai_studio_property
        for index, m in enumerate(oii.mask_images):
            if m.image and m.image.preview:
                box = column.box() if use_box else column.column(align=True)
                box.template_icon(m.image.preview.icon_id, scale=6)
                row = box.row(align=True)
                ops = row.operator("bas.select_mask", text=m.image.name, icon="RESTRICT_SELECT_OFF", translate=False)
                ops.index = index
                ops.remove = False
                ops = row.operator("bas.select_mask", text="", icon="TRASH")
                ops.index = index
                ops.remove = True
        if len(oii.mask_images) == 0:
            column.label(text="No mask available, please draw")


def add_reference_image(context, image, image_name=False):
    ai = context.scene.blender_ai_studio_property
    ri = ai.reference_images.add()
    ri.image = image
    ri.name = png_name_suffix(image.name, "_reference")
    if image_name:
        image.name = ri.name
    image.preview_ensure()


class SelectReferenceImageByFile(bpy.types.Operator, ImportHelper):
    bl_idname = "bas.select_reference_image_by_file"
    bl_label = "Select References By File"
    bl_translation_context = OPS_TCTX
    bl_options = {"REGISTER"}

    # File browser properties
    filename_ext = ""
    filter_glob: bpy.props.StringProperty(
        default="*.jpg;*.jpeg;*.png;*.bmp;*.tif;*.tiff;*.tga;*.exr;*.hdr",
        options={'HIDDEN'}
    )

    def execute(self, context):
        print(self.bl_idname, self.filepath)

        image = bpy.data.images.load(self.filepath)
        add_reference_image(context, image)
        return {"FINISHED"}


class SelectReferenceImageByImage(bpy.types.Operator):
    bl_idname = "bas.select_reference_image_by_image"
    bl_label = "Select References By Bl Image"
    bl_translation_context = OPS_TCTX
    bl_options = {"REGISTER"}

    icon_scale: bpy.props.FloatProperty(default=4, min=0.2, max=10, name="Icon Scale")

    def invoke(self, context, event):
        for i in bpy.data.images:
            if not i.preview:
                i.preview_ensure()
        wm = context.window_manager
        return wm.invoke_props_dialog(**{'operator': self, 'width': 300})

    def execute(self, context):
        image = getattr(context, "image", None)
        if image:
            print(self.bl_idname)
            add_reference_image(context, image)
            return {"FINISHED"}
        return {"CANCELLED"}

    def draw(self, context):
        ai = context.scene.blender_ai_studio_property
        layout = self.layout
        layout.prop(self, "icon_scale")
        for i in bpy.data.images:
            if i not in ai.all_references_images and not i.blender_ai_studio_property.is_mask_image:
                if i.preview:
                    box = layout.box()
                    row = box.row()
                    row.operator_context = "EXEC_DEFAULT"
                    row.context_pointer_set("image", i)
                    row.template_icon(i.preview.icon_id, scale=self.icon_scale)
                    col = row.column()
                    col.operator(self.bl_idname, text=i.name, translate=False, emboss=False, icon="RESTRICT_SELECT_OFF")
                else:
                    i.preview_ensure()


class ReplaceReferenceImage(bpy.types.Operator):
    bl_idname = "bas.replace_reference_image"
    bl_label = "Replace References"
    bl_translation_context = OPS_TCTX
    bl_options = {"REGISTER"}

    icon_scale: bpy.props.FloatProperty(default=4, min=0.2, max=10, name="Icon Scale")
    index: bpy.props.IntProperty()

    def invoke(self, context, event):
        for i in bpy.data.images:
            if not i.preview:
                i.preview_ensure()
        wm = context.window_manager
        return wm.invoke_props_dialog(**{'operator': self, 'width': 300})

    def execute(self, context):
        image = getattr(context, "image", None)
        if image:
            oii = context.scene.blender_ai_studio_property
            oii.reference_images[self.index].image = image
            print(self.bl_idname, image, self.index)
            return {"FINISHED"}
        return {"CANCELLED"}

    def draw(self, context):
        ai = context.scene.blender_ai_studio_property
        layout = self.layout
        layout.prop(self, "icon_scale")
        for i in bpy.data.images:
            if i not in ai.all_references_images and not i.blender_ai_studio_property.is_mask_image:
                if i.preview:
                    box = layout.box()
                    row = box.row()
                    row.operator_context = "EXEC_DEFAULT"
                    row.context_pointer_set("image", i)
                    row.template_icon(i.preview.icon_id, scale=self.icon_scale)
                    col = row.column()
                    col.operator(self.bl_idname, text=i.name, translate=False, emboss=False).index = self.index
                    col.operator(self.bl_idname, icon="RESTRICT_SELECT_OFF",
                                 text=bpy.app.translations.pgettext_iface("Replace References"),
                                 ).index = self.index
                else:
                    i.preview_ensure()


class RemoveReferenceImage(bpy.types.Operator):
    bl_idname = "bas.remove_reference_image"
    bl_label = "Remove References"
    bl_options = {"REGISTER"}

    index: bpy.props.IntProperty()

    def execute(self, context):
        ai = context.scene.blender_ai_studio_property
        ai.reference_images.remove(self.index)
        return {"FINISHED"}


class ApplyAiEditImage(bpy.types.Operator):
    bl_idname = "bas.apply_ai_edit_image"
    bl_description = "Apply AI Edit Image"
    bl_translation_context = OPS_TCTX
    bl_label = "Apply AI Edit"
    bl_options = {"REGISTER"}
    running_operator: bpy.props.StringProperty(default=bl_label, options={"HIDDEN", "SKIP_SAVE"})

    def invoke(self, context, event):
        self.execute(context)
        self._timer = context.window_manager.event_timer_add(1 / 60, window=context.window)
        context.window_manager.modal_handler_add(self)
        oii = context.scene.blender_ai_studio_property
        oii.start_running()
        return {"RUNNING_MODAL", "PASS_THROUGH"}

    def modal(self, context, event):
        oii = context.scene.blender_ai_studio_property
        if context.area:
            context.area.tag_redraw()

        if oii.running_state in (
                "completed",
                "failed",
                "cancelled",
        ):
            return {"FINISHED"}

        return {"PASS_THROUGH"}

    def execute(self, context):
        print(self.bl_idname)
        pref = get_pref()
        oii = context.scene.blender_ai_studio_property
        space_data = context.space_data
        image = space_data.image
        if not image:
            self.report({'ERROR'}, "No image")
            return {'CANCELLED'}

        if not oii.prompt.strip() and not len(oii.reference_images):  # 检查提示词和参考图片
            self.report({'ERROR'}, "Enter ai edit prompt or select reference images")
            return {'CANCELLED'}

        if not pref.nano_banana_api:
            self.report({'ERROR'}, "NANO API key not set, Enter it in addon preferences")
            return {'CANCELLED'}

        oii.running_operator = self.running_operator
        generate_image_name = f"{image.name}_{self.running_operator}"

        # 将blender图片保存到临时文件夹
        import tempfile
        temp_folder = tempfile.mkdtemp(prefix="bas_nano_banana_ai_image_")
        origin_image_file_path = save_image_to_temp_folder(image, temp_folder)
        reference_images_path = []
        mask_image_path = None

        if not origin_image_file_path:
            self.report({'ERROR'}, "Can't save image")
            return {'CANCELLED'}
        for ri in oii.reference_images:
            if ri.image:
                if rii := save_image_to_temp_folder(ri.image, temp_folder):
                    reference_images_path.append(rii)
                else:
                    self.report({'ERROR'}, "Can't save reference image")
                    return {'CANCELLED'}
            else:
                self.report({'ERROR'}, "Can't save reference image")
                return {'CANCELLED'}
        if oii.active_mask:
            if mask_path := save_image_to_temp_folder(oii.active_mask, temp_folder):
                mask_image_path = mask_path
            else:
                self.report({'ERROR'}, "Can't save mask image")
                return {'CANCELLED'}

        print("temp", temp_folder)
        print("reference_images_path", reference_images_path)
        from .tasks import GeminiImageEditTask, Task, TaskState, TaskResult, TaskManager
        task = GeminiImageEditTask(
            api_key=pref.nano_banana_api,
            image_path=origin_image_file_path,
            edit_prompt=oii.prompt,
            mask_path=mask_image_path,
            reference_images_path=reference_images_path,
            aspect_ratio=oii.aspect_ratio,
            resolution=oii.resolution,
            max_retries=1,
        )
        oii.running_message = "Start..."

        # 2. 注册回调
        def on_state_changed(event_data):
            _task: Task = event_data["task"]
            old_state: TaskState = event_data["old_state"]
            new_state: TaskState = event_data["new_state"]
            print(f"状态改变: {old_state.value} -> {new_state.value}")
            oii.running_state = new_state.value

        def on_progress(event_data):
            # {
            #     "current_step": 2,
            #     "total_steps": 4,
            #     "percentage": 0.5,
            #     "message": "正在调用 API...",
            #     "details": {},
            # }
            _task: Task = event_data["task"]
            progress: dict = event_data["progress"]
            percent = progress["percentage"]
            message = progress["message"]
            p = bpy.app.translations.pgettext('Progress')
            text = f"{p}: {percent * 100}% - {message}"
            print(text)
            oii.running_message = text

        def on_completed(event_data):
            # result_data = {
            #     "image_data": b"",
            #     "mime_type": "image/png",
            #     "width": 1024,
            #     "height": 1024,
            # }
            oii.origin_image = image
            _task: Task = event_data["task"]
            result: TaskResult = event_data["result"]
            result_data: dict = result.data
            # 存储结果
            save_file = Path(temp_folder).joinpath(f"{generate_image_name}_Output.png")
            save_file.write_bytes(result_data["image_data"])
            text = f"任务完成: {_task.task_id}"
            print(text, save_file)
            oii.running_message = "Running completed"

            import bpy
            if gi := bpy.data.images.load(str(save_file), check_existing=False):
                oii.generated_image = gi
                gi.preview_ensure()
                gi.name = generate_image_name
                try:
                    space_data.image = gi
                except Exception as e:
                    print("error", e)
                    import traceback
                    traceback.print_exc()
                    traceback.print_stack()
            else:
                ut = bpy.app.translations.pgettext("Unable to load generated image!")
                oii.running_message = ut + " " + str(save_file)
            oii.stop_running()
            oii.save_to_history()

        def on_failed(event_data):
            print("on_failed", event_data)
            _task: Task = event_data["task"]
            result: TaskResult = event_data["result"]
            if not result.success:
                print(result.error)
                oii.running_message = str(result.error)
            else:
                oii.running_message = "Unknown error" + " " + str(result.data)
            oii.stop_running()

        task.register_callback("state_changed", on_state_changed)
        task.register_callback("progress_updated", on_progress)
        task.register_callback("completed", on_completed)
        task.register_callback("failed", on_failed)
        TaskManager.get_instance().submit_task(task)
        print(f"任务提交: {task.task_id}")
        print("task", task)
        return {"FINISHED"}


class SmartFixImage(bpy.types.Operator):
    bl_idname = "bas.smart_fix"
    bl_description = "Smart Fix"
    bl_translation_context = OPS_TCTX
    bl_label = "Smart Fix"
    bl_options = {"REGISTER"}

    def execute(self, context):
        print(self.bl_idname)
        oii = context.scene.blender_ai_studio_property
        oii.prompt = "[智能修复]"

        self.report({'INFO'}, "Smart Fix - unifying colors, contrast, lighting...")
        bpy.ops.bas.apply_ai_edit_image("INVOKE_DEFAULT", running_operator=self.bl_label)
        return {"FINISHED"}


class ReRenderImage(bpy.types.Operator):
    bl_idname = "bas.rerender_image"
    bl_translation_context = OPS_TCTX
    bl_label = "ReRender Image"
    bl_options = {"REGISTER"}
    bl_description = "Generate a new variation with the same prompt and settings"

    def execute(self, context):
        print(self.bl_idname)
        oii = context.scene.blender_ai_studio_property

        image = context.space_data.image

        if not image:
            self.report({'ERROR'}, "No image in editor")
            return {'CANCELLED'}

        if len(oii.history) == 0:
            self.report({'INFO'}, "No history - use 'Apply AI Edit' first")
            return {'CANCELLED'}
        last = oii.history[-1]
        oii.prompt = last.prompt

        bpy.ops.bas.apply_ai_edit_image("INVOKE_DEFAULT", running_operator=self.bl_label)
        self.report({'INFO'}, "Re-rendering with previous settings...")
        return {"FINISHED"}


def get_text_data(context) -> bpy.types.Text:
    """
    获取脚本数据块

    :param context:
    :return:
    """
    prompt = context.scene.blender_ai_studio_property.prompt

    name = "Prompt"
    text = bpy.data.texts.get(name)
    if text is None:
        text = bpy.data.texts.new(name)
    text.clear()
    text.write(prompt)
    text.blender_ai_studio_prompt_hash = str(hash(prompt))
    return text


class PromptEdit(bpy.types.Operator):
    bl_idname = 'bas.prompt_edit'
    bl_label = 'Prompt Edit'

    @staticmethod
    def add_save_key(context):
        keymap = get_text_generic_keymap(context)
        if keymap is not None:
            keymap.keymap_items.new(PromptSave.bl_idname, type="S", value="PRESS", ctrl=True)

    def execute(self, context):
        get_text_window(context, get_text_data(context))
        self.add_save_key(context)
        return {'FINISHED'}


def draw_save_script_button(self, context):
    layout = self.layout

    text = context.space_data.text
    prompt = context.scene.blender_ai_studio_property.prompt

    # layout.prop(text, "blender_ai_studio_prompt_hash")
    # layout.label(text=str(hash(prompt)))
    if getattr(text, "blender_ai_studio_prompt_hash", False) == str(hash(prompt)):
        row = layout.row()
        row.alert = True
        text = bpy.app.translations.pgettext("Save Prompt Ctrl + S")
        row.operator(PromptSave.bl_idname, text=text)


class PromptSave(bpy.types.Operator):
    bl_label = 'Save script'
    bl_idname = 'bas.prompt_save'

    @classmethod
    def poll(cls, context):
        pref = get_pref()
        prompt = context.scene.blender_ai_studio_property.prompt
        h = context.space_data.text.blender_ai_studio_prompt_hash
        hash_ok = h == str(hash(prompt))
        return hash_ok

    @staticmethod
    def register_ui():
        bpy.types.TEXT_HT_header.append(draw_save_script_button)

    @staticmethod
    def unregister_ui():
        bpy.types.TEXT_HT_header.remove(draw_save_script_button)

    def remove_save_key(self, context):
        keymap = get_text_generic_keymap(context)
        if keymap is not None:
            while True:
                ops = keymap.keymap_items.find_from_operator(self.bl_idname)
                if ops is None:
                    break
                keymap.keymap_items.remove(ops)

    def execute(self, context):
        text = context.space_data.text
        context.scene.blender_ai_studio_property.prompt = text.as_string()
        bpy.data.texts.remove(text)
        self.remove_save_key(context)
        bpy.ops.wm.window_close()
        return {'FINISHED'}


class ViewImage(bpy.types.Operator):
    bl_idname = 'bas.view_image'
    bl_label = 'View Image'
    bl_translation_context = OPS_TCTX
    bl_options = {"REGISTER"}
    bl_description = "View image"

    @classmethod
    def poll(cls, context):
        return hasattr(context.space_data, "image")

    def execute(self, context):
        image = getattr(context, "image", None)
        print(self.bl_idname, image)
        if not image:
            self.report({'ERROR'}, "No image")
            return {'CANCELLED'}
        if image.preview:
            image.preview.reload()
        else:
            image.preview_ensure()
        setattr(context.space_data, "image", image)
        return {"FINISHED"}


class RestoreHistory(bpy.types.Operator):
    bl_idname = 'bas.restore_history'
    bl_label = 'Restore History'
    bl_translation_context = OPS_TCTX
    bl_options = {"REGISTER"}
    bl_description = "Restore ai edit history"

    @classmethod
    def poll(cls, context):
        return hasattr(context, "history")

    @classmethod
    def description(cls, context, properties):
        history = getattr(context, "history")
        if history:
            text = bpy.app.translations.pgettext("Restore ai edit history")
            return f"{text}\n%s" % history.more_history_information
        return "Restore ai edit history"

    def execute(self, context):
        history = getattr(context, "history")
        print(self.bl_idname, history)
        history.restore_history(context)
        return {"FINISHED"}


class OpenImageInNewWindow(bpy.types.Operator):
    bl_idname = 'bas.open_image_in_new_window'
    bl_label = 'Open Image In New Window'
    bl_translation_context = OPS_TCTX
    bl_options = {"REGISTER"}
    bl_description = "Open image in new window"

    image_path: bpy.props.StringProperty()
    data: bpy.props.StringProperty()

    run_count: bpy.props.IntProperty(default=0)

    @staticmethod
    def get_image_window(context):
        wm = context.window_manager

        # 获取一个新窗口
        if len(wm.windows) > 1:
            last_window = wm.windows[-1]
            if len(last_window.screen.areas[:]) == 1:
                last_area = last_window.screen.areas[0]
                if last_area.type == "IMAGE_EDITOR":
                    return last_window
        return None

    def invoke(self, context, event):
        self.load_data(context)
        image_window = self.get_image_window(context)
        if image_window:
            return self.execute(context)
        else:
            bpy.ops.wm.window_new("EXEC_DEFAULT", False)
            last_window = bpy.context.window_manager.windows[-1]
            last_window.screen.areas[0].type = "IMAGE_EDITOR"

            context.window_manager.modal_handler_add(self)
            return {"RUNNING_MODAL"}

    def load_data(self, context):
        try:
            data = json.loads(self.data)
            metadata = data.get("metadata", None)
            if metadata:
                aspect_ratio = metadata.get("aspect_ratio", "1:1")
                oii = context.scene.blender_ai_studio_property
                resolution = metadata.get("resolution", "1K")
                oii.aspect_ratio = aspect_ratio
                oii.resolution = resolution
        except Exception as e:
            print(e)
            print("load_data error", self.data)

    def modal(self, context, event):
        return self.execute(context)

    def execute(self, context):
        try:
            image_window = self.get_image_window(context)
            if not image_window:
                self.report({'ERROR'}, "No image window")
                return {'CANCELLED'}
            if image_window:
                image = load_image(self.image_path)
                if image is None:
                    self.report({'ERROR'}, "No image" + self.image_path)
                    return {'CANCELLED'}
                for area in image_window.screen.areas:
                    if area.type == "IMAGE_EDITOR":
                        for space in area.spaces:
                            if space.type == "IMAGE_EDITOR":
                                space.image = image
                                space.show_region_ui = True
                                region = area.regions[4]
                                if region.active_panel_category == "UNSUPPORTED":  # 如果还是不支持说明还没被渲染或初始化,再等待多一会
                                    self.run_count += 1
                                    if self.run_count > 20:  # 最多等待20次
                                        self.report({'ERROR'}, "No image area")
                                        return {'CANCELLED'}
                                    return {"RUNNING_MODAL"}
                                region.active_panel_category = "AIStudio"  # 设置活动面板
                                # bpy.ops.image.view_all() #崩溃会
                                bpy.ops.image.view_all(fit_view=True)
                                return {"FINISHED"}
                self.report({'ERROR'}, "No image area")
        except Exception as e:
            print(e)
            import traceback
            traceback.print_exc()
            traceback.print_stack()
        return {'CANCELLED'}


clss = [
    AIStudioEntry,
    FileImporter,
    FileExporter,

    SelectMask,
    DrawImageMask,
    ApplyImageMask,

    RemoveReferenceImage,
    SelectReferenceImageByFile,
    SelectReferenceImageByImage,
    ReplaceReferenceImage,

    ApplyAiEditImage,
    SmartFixImage,
    ReRenderImage,

    PromptEdit,
    PromptSave,

    ViewImage,
    RestoreHistory,

    OpenImageInNewWindow,
]

reg, unreg = bpy.utils.register_classes_factory(clss)


def register():
    reg()
    PromptSave.register_ui()


def unregister():
    unreg()
    PromptSave.unregister_ui()
