from pathlib import Path

import bpy

from .. import logger
from ..i18n.translations.zh_HANS import OPS_TCTX
from ..utils import png_name_suffix, get_pref, get_temp_folder, save_image_to_temp_folder


class ApplyAiEditImage(bpy.types.Operator):
    bl_idname = "bas.apply_ai_edit_image"
    bl_description = "Apply AI Edit Image"
    bl_translation_context = OPS_TCTX
    bl_label = "Apply AI Edit"
    bl_options = {"REGISTER"}
    running_operator: bpy.props.StringProperty(default=bl_label, options={"HIDDEN", "SKIP_SAVE"})

    task = None

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
        print(self.bl_idname, "start")
        pref = get_pref()
        oii = context.scene.blender_ai_studio_property
        space_data = context.space_data
        image = space_data.image
        aspect_ratio = oii.get_out_aspect_ratio(context)
        resolution = oii.get_out_resolution(context)
        if not image:
            self.report({"ERROR"}, "No image")
            return {"CANCELLED"}

        if not oii.prompt.strip() and not len(oii.reference_images):  # 检查提示词和参考图片
            self.report({"ERROR"}, "Enter ai edit prompt or select reference images")
            return {"CANCELLED"}

        if pref.is_backup_mode:
            ...
        else:
            if not pref.nano_banana_api:
                self.report({"ERROR"}, "NANO API key not set, Enter it in addon preferences")
                return {"CANCELLED"}

        oii.running_operator = self.running_operator
        generate_image_name = png_name_suffix(image.name, f"_{self.running_operator}")

        # 将blender图片保存到临时文件夹
        temp_folder = get_temp_folder(prefix="edit")

        origin_image_file_path = save_image_to_temp_folder(image, temp_folder)
        reference_images_path = []
        mask_image_path = None

        if not origin_image_file_path:
            self.report({"ERROR"}, "Can't save image")
            return {"CANCELLED"}
        for ri in oii.reference_images:
            if ri.image:
                if rii := save_image_to_temp_folder(ri.image, temp_folder):
                    reference_images_path.append(rii)
                else:
                    self.report({"ERROR"}, "Can't save reference image")
                    return {"CANCELLED"}
            else:
                self.report({"ERROR"}, "Can't save reference image")
                return {"CANCELLED"}
        if oii.active_mask:
            if mask_path := save_image_to_temp_folder(oii.active_mask, temp_folder):
                mask_image_path = mask_path
            else:
                self.report({"ERROR"}, "Can't save mask image")
                return {"CANCELLED"}

        print("temp", temp_folder)
        print("reference_images_path", reference_images_path)
        print("mask_image_path", mask_image_path)
        print("aspect_ratio", aspect_ratio)
        print("resolution", resolution)
        from ..studio.account import Account
        from ..studio.tasks import GeminiImageEditTask, AccountGeminiImageEditTask, Task, TaskState, TaskResult, \
            TaskManager
        from ..preferences import AuthMode

        task_type_map = {
            AuthMode.ACCOUNT.value: AccountGeminiImageEditTask,
            AuthMode.API.value: GeminiImageEditTask,
        }
        account = Account.get_instance()
        TaskType = task_type_map[account.auth_mode]
        api_key = pref.nano_banana_api if account.auth_mode == AuthMode.API.value else account.token

        task = TaskType(
            api_key=api_key,
            image_path=origin_image_file_path,
            edit_prompt=oii.prompt,
            mask_path=mask_image_path,
            reference_images_path=reference_images_path,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            max_retries=1,
        )
        oii.running_message = "Start..."

        # 2. 注册回调
        def on_state_changed(event_data):
            def f():
                _task: Task = event_data["task"]
                old_state: TaskState = event_data["old_state"]
                new_state: TaskState = event_data["new_state"]
                text = f"状态改变: {old_state.value} -> {new_state.value}"
                ai_oii = bpy.context.scene.blender_ai_studio_property
                ai_oii.running_state = new_state.value
                logger.info(text)
            bpy.app.timers.register(f, first_interval=0.1)

        def on_progress(event_data):
            def f():
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
                p = bpy.app.translations.pgettext("Progress")
                text = f"{p}: {percent * 100}% - {message}"

                ai_oii = bpy.context.scene.blender_ai_studio_property
                ai_oii.running_message = text
                logger.info(text)
            bpy.app.timers.register(f, first_interval=0.1)

        def on_completed(event_data):
            def f():
                # result_data = {
                #     "image_data": b"",
                #     "mime_type": "image/png",
                #     "width": 1024,
                #     "height": 1024,
                # }

                ai_oii = bpy.context.scene.blender_ai_studio_property
                ai_oii.origin_image = image
                _task: Task = event_data["task"]
                result: TaskResult = event_data["result"]
                result_data: dict = result.data
                # 存储结果
                save_file = Path(temp_folder).joinpath(f"{generate_image_name}_Output.png")
                save_file.write_bytes(result_data["image_data"])
                text = f"任务完成: {_task.task_id} {save_file}"
                ai_oii.running_message = "Running completed"

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
                    ai_oii.running_message = ut + " " + str(save_file)
                ai_oii.stop_running()
                ai_oii.save_to_history()
                logger.info(text)
            bpy.app.timers.register(f, first_interval=0.1)

        def on_failed(event_data):
            def f():
                text = f"on_failed {event_data}"
                logger.info(text)

                ai_oii = bpy.context.scene.blender_ai_studio_property

                _task: Task = event_data["task"]
                result: TaskResult = event_data["result"]
                if not result.success:
                    ai_oii.running_message = str(result.error)
                    logger.info(ai_oii.running_message)
                else:
                    ai_oii.running_message = "Unknown error" + " " + str(result.data)
                ai_oii.stop_running()
            bpy.app.timers.register(f, first_interval=0.1)

        task.register_callback("state_changed", on_state_changed)
        task.register_callback("progress_updated", on_progress)
        task.register_callback("completed", on_completed)
        task.register_callback("failed", on_failed)
        TaskManager.get_instance().submit_task(task)
        logger.info(f"任务提交: {task.task_id}")
        self.task = task
        return {"FINISHED"}

    def cancel(self, context):
        logger.info("task cancel")
        if self.task:
            self.task.cancel()


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

        self.report({"INFO"}, "Smart Fix - unifying colors, contrast, lighting...")
        try:
            bpy.ops.bas.apply_ai_edit_image("INVOKE_DEFAULT", running_operator=self.bl_label)
        except Exception as e:
            self.report({"ERROR"}, str(e))
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
            self.report({"ERROR"}, "No image in editor")
            return {"CANCELLED"}

        if len(oii.history) == 0:
            self.report({"INFO"}, "No history - use 'Render' first")
            return {"CANCELLED"}
        last = oii.history[-1]
        oii.prompt = last.prompt

        self.report({"INFO"}, "Re-rendering with previous settings...")

        try:
            bpy.ops.bas.apply_ai_edit_image("INVOKE_DEFAULT", running_operator=self.bl_label)
        except Exception as e:
            self.report({"ERROR"}, str(e))
        return {"FINISHED"}
