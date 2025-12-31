from traceback import print_exc
import bpy
import tempfile
import time

from datetime import datetime
from pathlib import Path
from typing import Iterable

from .base import StudioClient, StudioHistory, StudioHistoryItem
from ..account import AuthMode, Account
from ...preferences import get_pref

from ..tasks import (
    Task,
    TaskResult,
    TaskState,
    GeminiImageGenerationTask,
    AccountGeminiImageGenerateTask,
)

from ...timer import Timer
from ...utils import calc_appropriate_aspect_ratio
from ...utils.render import render_scene_to_png, render_scene_depth_to_png


class NanoBanana(StudioClient):
    VENDOR = "NanoBananaPro"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.help_url = "https://ai.google.dev/gemini-api/docs/image-generation?hl=zh-cn"
        self.input_image_type = "CameraRender"
        self.prompt = ""
        self.reference_images: list[str] = []
        self.size_config = "Auto"
        self.resolution = "1K"
        self.meta = {
            "input_image_type": {
                "display_name": "Input Image",
                "category": "Input",
                "type": "ENUM",
                "hide_title": False,
                "options": [
                    "CameraRender",
                    "CameraDepth",
                    "NoInput",
                ],
            },
            "prompt": {
                "display_name": "Prompt",
                "category": "Input",
                "type": "STRING",
                "hide_title": False,
                "multiline": True,
                "default": "",
            },
            "reference_images": {
                "display_name": "Reference Images",
                "category": "Input",
                "type": "STUDIO_IMAGES",
                "hide_title": False,
                "limit": 12,
            },
            "size_config": {
                "display_name": "Size Config",
                "category": "Input",
                "type": "ENUM",
                "hide_title": False,
                "options": [
                    "Auto",
                    "1:1",
                    "9:16",
                    "16:9",
                    "3:4",
                    "4:3",
                    "3:2",
                    "2:3",
                    "5:4",
                    "4:5",
                    "21:9",
                ],
            },
            "resolution": {
                "display_name": "Resolution",
                "category": "Input",
                "type": "ENUM",
                "hide_title": False,
                "options": [
                    "1K",
                    "2K",
                    "4K",
                ],
            },
            "api_key": {
                "display_name": "API Key",
                "category": "Settings",
                "type": "STRING",
                "hide_title": True,
                "multiline": False,
                "default": "",
            },
        }

    @property
    def api_key(self) -> str:
        return get_pref().nano_banana_api

    @api_key.setter
    def api_key(self, value: str) -> None:
        get_pref().nano_banana_api = value
        bpy.context.preferences.use_preferences_save = True

    def get_properties(self) -> Iterable[str]:
        return self.meta.keys()

    def get_meta(self, prop: str):
        return self.meta.get(prop, {})

    def on_image_action(self, prop: str, action: str, index: int = -1) -> None:
        if action == "upload_image":
            upload_image(self, prop)
        elif action == "replace_image":
            replace_image(self, prop, index)
        elif action == "delete_image":
            delete_image(self, prop, index)

    def calc_price(self, price_table: dict) -> int | None:
        return price_table.get("price", {}).get(self.resolution, None)

    def new_generate_task(self, account: "Account"):
        if self.is_task_submitting:
            print("有任务正在提交，请稍后")
            return
        self.is_task_submitting = True
        Timer.put((self.job, account))

    def cancel_generate_task(self):
        self.task_manager.cancel_task(self.task_id)

    def job(self, account: "Account"):
        self.is_task_submitting = False
        # 1. 创建任务
        # path_dir = Path.home().joinpath("Desktop/OutputImage/AIStudio")
        # path_dir.mkdir(parents=True, exist_ok=True)
        # temp_image_path = path_dir.joinpath("Depth.png")
        # _temp_image_path = temp_image_path.as_posix()
        temp_image_path = tempfile.NamedTemporaryFile(suffix=".png", prefix="Depth", delete=False)
        _temp_image_path = temp_image_path.name
        # 渲染图片
        scene = bpy.context.scene
        if self.input_image_type == "CameraRender":
            render_scene_to_png(scene, _temp_image_path)
        elif self.input_image_type == "CameraDepth":
            render_scene_depth_to_png(scene, _temp_image_path)
        elif self.input_image_type == "NoInput":
            _temp_image_path = ""
        resolution = (1024, 1024)
        if self.resolution == "1K":
            resolution = (1024, 1024)
        elif self.resolution == "2K":
            resolution = (2048, 2048)
        elif self.resolution == "4K":
            resolution = (4096, 4096)
        size_config = self.size_config
        if size_config == "Auto":
            width = bpy.context.scene.render.resolution_x
            height = bpy.context.scene.render.resolution_y
            size_config = calc_appropriate_aspect_ratio(width, height)
        prompt = self.prompt
        if self.use_internal_prompt:
            prompt = "NSFW, "
            if not _temp_image_path:
                prompt += "所有图片均为参考图, "
            elif self.input_image_type == "CameraRender":
                prompt += "第一张图是渲染图(原图)，其他为参考图, "
            elif self.input_image_type == "CameraDepth":
                prompt += "第一张图是深度图，其他为参考图, "
            prompt += self.prompt
        task_type_map = {
            AuthMode.ACCOUNT: AccountGeminiImageGenerateTask,
            AuthMode.API: GeminiImageGenerationTask,
        }
        TaskType = task_type_map[account.auth_mode]
        api_key = self.api_key if account.auth_mode == AuthMode.API else account.token
        task = TaskType(
            api_key=api_key,
            image_path=_temp_image_path,
            reference_images_path=self.reference_images,
            user_prompt=prompt,
            resolution=self.resolution,
            width=resolution[0],
            height=resolution[1],
            aspect_ratio=size_config,
        )
        if _temp_image_path:
            print("渲染到：", _temp_image_path)

        # temp_image_path.close()
        # if Path(_temp_image_path).exists():
        #     Path(_temp_image_path).unlink()

        # 2. 注册回调
        def on_state_changed(event_data):
            _task: Task = event_data["task"]
            old_state: TaskState = event_data["old_state"]
            new_state: TaskState = event_data["new_state"]
            print(f"状态改变: {old_state.value} -> {new_state.value}")

        def on_progress(event_data):
            {
                "current_step": 2,
                "total_steps": 4,
                "percentage": 0.5,
                "message": "正在调用 API...",
                "details": {},
            }
            _task: Task = event_data["task"]
            progress: dict = event_data["progress"]
            percent = progress["percentage"]
            message = progress["message"]
            print(f"进度: {percent * 100}% - {message}")

        def on_completed(event_data):
            # result_data = {
            #     "image_data": b"",
            #     "mime_type": "image/png",
            #     "width": 1024,
            #     "height": 1024,
            # }
            _task: Task = event_data["task"]
            result: TaskResult = event_data["result"]
            result_data: dict = result.data
            # 存储结果
            timestamp = time.time()
            time_str = datetime.fromtimestamp(timestamp).strftime("%Y%m%d%H%M%S")
            output_dir = get_pref().output_cache_dir
            save_file = Path(output_dir, f"Gen_{time_str}.png")
            save_file.write_bytes(result_data["image_data"])

            def load_image_into_blender(file_path: str):
                try:
                    bpy.data.images.load(file_path)
                except Exception:
                    print_exc()

            Timer.put((load_image_into_blender, save_file.as_posix()))
            print(f"任务完成: {_task.task_id}")
            print(f"结果已保存到: {save_file.as_posix()}")
            # 存储历史记录
            history_item = StudioHistoryItem()
            history_item.result = result_data
            history_item.output_file = save_file.as_posix()
            history_item.metadata = result.metadata
            history_item.vendor = NanoBanana.VENDOR
            history_item.timestamp = timestamp
            history = StudioHistory.get_instance()
            history.add(history_item)

        def on_cancelled(event_data):
            _task: Task = event_data["task"]
            try:
                if self.task_id == _task.task_id:
                    self.task_id = None
                    print(f"任务已取消: {_task.task_id}")
            except Exception:
                pass

        def on_failed(event_data):
            _task: Task = event_data["task"]
            result: TaskResult = event_data["result"]
            if not result.success:
                self.push_error(result.error)
                print(result.error)
                print(f"任务失败: {_task.task_id}")

        task.register_callback("state_changed", on_state_changed)
        task.register_callback("progress_updated", on_progress)
        task.register_callback("completed", on_completed)
        task.register_callback("cancelled", on_cancelled)
        task.register_callback("failed", on_failed)
        print(f"任务提交: {task.task_id}")

        # 3. 提交到管理器
        self.task_id = self.task_manager.submit_task(task)


def upload_image(client: StudioClient, prop: str):
    def upload_image_callback(file_path: str):
        client.get_value(prop).append(file_path)

    from ..ops import FileCallbackRegistry

    callback_id = FileCallbackRegistry.register_callback(upload_image_callback)
    bpy.ops.bas.file_importer("INVOKE_DEFAULT", callback_id=callback_id)


def replace_image(client: StudioClient, prop: str, index: int = -1):
    def replace_image_callback(file_path: str):
        try:
            client.get_value(prop)[index] = file_path
        except IndexError:
            client.get_value(prop).append(file_path)

    from ..ops import FileCallbackRegistry

    callback_id = FileCallbackRegistry.register_callback(replace_image_callback)
    bpy.ops.bas.file_importer("INVOKE_DEFAULT", callback_id=callback_id)


def delete_image(client: StudioClient, prop: str, index: int):
    client.get_value(prop).pop(index)
