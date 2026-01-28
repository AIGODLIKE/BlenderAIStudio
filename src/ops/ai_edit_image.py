import json
import mimetypes
from pathlib import Path

import bpy

from .. import logger
from ..i18n.translations.zh_HANS import OPS_TCTX
from ..utils import png_name_suffix, get_pref, get_temp_folder, save_image_to_temp_folder, refresh_image_preview


class ApplyAiEditImage(bpy.types.Operator):
    bl_idname = "bas.apply_ai_edit_image"
    bl_description = "Apply AI Edit Image"
    bl_translation_context = OPS_TCTX
    bl_label = "Apply AI Edit"
    bl_options = {"REGISTER"}
    running_operator: bpy.props.StringProperty(default=bl_label, options={"HIDDEN", "SKIP_SAVE"})

    _timer = None

    def invoke(self, context, event):
        print()
        self.execute(context)

        if self.__class__._timer is None:
            self.__class__._timer = context.window_manager.event_timer_add(1 / 60, window=context.window)
            context.window_manager.modal_handler_add(self)
            return {"RUNNING_MODAL", "PASS_THROUGH"}
        return {"FINISHED"}

    def exit(self, context):
        if self.__class__._timer:
            context.window_manager.event_timer_remove(self.__class__._timer)
        if context.area:
            context.area.tag_redraw()

    def modal(self, context, event):
        oii = context.scene.blender_ai_studio_property
        if context.area:
            context.area.tag_redraw()

        if len(oii.running_task_list) == 0:  # 所有的任务都没了,不刷新界面了
            return {"FINISHED"}
        return {"PASS_THROUGH"}

    def execute(self, context):
        print(self.bl_idname, "start")
        pref = get_pref()
        oii = context.scene.blender_ai_studio_property
        space_data = context.space_data
        origin_image = space_data.image
        aspect_ratio = oii.aspect_ratio
        resolution = oii.resolution
        if not origin_image:
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

        generate_image_name = png_name_suffix(origin_image.name, f"_{self.running_operator}")

        # 将blender图片保存到临时文件夹
        temp_folder = get_temp_folder(prefix="edit")

        origin_image_file_path = save_image_to_temp_folder(origin_image, temp_folder)
        reference_images_path = []
        mask_image_path = ""

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
        try:
            self.task_start(
                context, resolution,
                aspect_ratio,
                origin_image,
                origin_image_file_path,
                reference_images_path,
                mask_image_path,
                temp_folder,
                generate_image_name,
            )
        except Exception as e:
            self.cancel(context)
            logger.error(str(e))
            self.report({"ERROR"}, str(e))
        return {"FINISHED"}

    def cancel(self, context):
        self.exit(context)

    def task_start(self,
                   context,
                   resolution,
                   aspect_ratio,
                   origin_image,
                   origin_image_file_path,
                   reference_images_path,
                   mask_image_path,
                   temp_folder,
                   generate_image_name,
                   ):

        from ..studio.tasks import UniversalModelTask, TaskManager, TaskResult, TaskState, Task
        from ..studio.account import Account
        from ..studio.config.model_registry import ModelRegistry

        from ..preferences import AuthMode

        space_data = context.space_data
        pref = get_pref()
        oii = context.scene.blender_ai_studio_property

        account = Account.get_instance()
        model_registry = ModelRegistry.get_instance()
        model_name = oii.model  # "gemini-3-pro-image-preview"
        model_id = model_registry.resolve_model_id(model_name, account.auth_mode)

        # 创建历史记录 ,在这个时候就需要保存信息了
        edit_history = oii.edit_history.add()  # 添加历史记录,将当前任务加入历史记录，历史记录当做一个任务进行显示
        edit_history.start_running(model_name)
        edit_history.running_operator = self.running_operator
        edit_history.prompt = oii.prompt
        edit_history.origin_image = origin_image
        edit_history.mask_index = oii.mask_index
        refresh_image_preview(origin_image)

        logger.info(f"model_name: {model_name} auth_mode: {account.auth_mode}")

        if account.auth_mode == AuthMode.API.value:
            credentials = {"api_key": pref.from_model_name_get_api_key(model_name)}
        else:
            submit_model_id = model_registry.resolve_submit_id(model_name, account.auth_mode, )
            credentials = {
                "token": account.token,
                "modelId": submit_model_id,
                "size": resolution,
            }
        reference_images = [mask_image_path, *reference_images_path]  # 优先传递mask图片(即使为空)
        params = {
            "main_image": origin_image_file_path,
            "prompt": oii.prompt,
            "reference_images": reference_images,
            "resolution": resolution,
            "aspect_ratio": aspect_ratio,
            "__use_internal_prompt": False,
            "__action": "edit",
        }

        ww = credentials.copy()
        ww.pop("token")
        logger.info(f"credentials {json.dumps(ww, indent=4)}")
        logger.info(f"params {json.dumps(params, indent=4)}")

        task = UniversalModelTask(
            model_id=model_name,
            auth_mode=account.auth_mode,
            credentials=credentials,
            params=params,
            context=bpy.context.copy(),
        )

        edit_history.running_message = "Start..."

        # 2. 注册回调
        def on_state_changed(event_data):
            def f():
                _task: Task = event_data["task"]
                old_state: TaskState = event_data["old_state"]
                new_state: TaskState = event_data["new_state"]
                text = f"状态改变: {old_state.value} -> {new_state.value}"
                edit_history.running_state = new_state.value
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

                edit_history.running_message = text
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

                _task: Task = event_data["task"]
                result: TaskResult = event_data["result"]
                results: list[tuple[str, str | bytes]] = result.data
                if not results:
                    logger.warning("No results")
                    return

                # 存储结果
                result_data = results[0]
                ext = mimetypes.guess_extension(result_data[0])
                save_file = Path(temp_folder).joinpath(f"{generate_image_name}_Output{ext}")
                save_file.write_bytes(result_data[1])
                text = f"任务完成: {_task.task_id} {save_file}"

                edit_history.running_message = "Running completed"

                if gi := bpy.data.images.load(str(save_file), check_existing=False):
                    edit_history.generated_image = gi
                    gi.preview_ensure()
                    gi.name = generate_image_name
                    try:
                        space_data.image = gi
                    except Exception as e:
                        print("生成完成设置生成图像到活动项错误 error", e)
                        import traceback

                        traceback.print_exc()
                        traceback.print_stack()
                else:
                    ut = bpy.app.translations.pgettext("Unable to load generated image!")
                    edit_history.running_message = ut + " " + str(save_file)

                edit_history.stop_running()
                logger.info(text)

            bpy.app.timers.register(f, first_interval=0.1)

        def on_failed(event_data):
            def f():
                text = f"on_failed {event_data}"
                logger.info(text)

                _task: Task = event_data["task"]
                result: TaskResult = event_data["result"]
                if not result.success:
                    edit_history.running_message = str(result.error)
                    logger.info(edit_history.running_message)
                else:
                    edit_history.running_message = "Unknown error" + " " + str(result.data)
                edit_history.stop_running()

            bpy.app.timers.register(f, first_interval=0.1)

        task.register_callback("state_changed", on_state_changed)
        task.register_callback("progress_updated", on_progress)
        task.register_callback("completed", on_completed)
        task.register_callback("failed", on_failed)
        TaskManager.get_instance().submit_task(task)
        logger.info(f"任务提交: {task.task_id}")


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

        if len(oii.edit_history) == 0:
            self.report({"INFO"}, "No history - use 'Render' first")
            return {"CANCELLED"}
        last = oii.edit_history[-1]
        oii.prompt = last.prompt

        self.report({"INFO"}, "Re-rendering with previous settings...")

        try:
            bpy.ops.bas.apply_ai_edit_image("INVOKE_DEFAULT", running_operator=self.bl_label)
        except Exception as e:
            self.report({"ERROR"}, str(e))
        return {"FINISHED"}
