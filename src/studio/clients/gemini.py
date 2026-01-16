import tempfile
import time
from datetime import datetime
from pathlib import Path
from threading import Thread
from traceback import print_exc
from typing import Iterable

import bpy
from bpy.app.translations import pgettext_iface as _T

from .base import StudioClient, StudioHistory, StudioHistoryItem
from ..account import Account
from ..tasks import (
    Task,
    TaskResult,
    TaskState,
    GeminiImageGenerationTask,
    AccountGeminiImageGenerateTask,
)
from ... import logger
from ...preferences import AuthMode
from ...timer import Timer
from ...utils import calc_appropriate_aspect_ratio, get_temp_folder, get_pref
from ...utils.render import render_scene_to_png, render_scene_depth_to_png, RenderAgent, check_image_valid


class NanoBanana(StudioClient):
    VENDOR = "NanoBananaPro"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.is_rendering = False
        self.render_cancel = False

        self.rendering_time_start = 0
        self.input_image_type = "CameraRender"
        self.help_url = "https://ai.google.dev/gemini-api/docs/image-generation?hl=zh-cn"
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

    def query_status(self) -> dict:
        if self.is_rendering:
            return {
                "state": "rendering",
                "elapsed_time": self.get_rendering_time(),
            }
        return super().query_status()

    def get_rendering_time(self) -> float:
        return time.time() - self.rendering_time_start

    def on_image_action(self, prop: str, action: str, index: int = -1) -> None:
        if action == "upload_image":
            upload_image(self, prop)
        elif action == "replace_image":
            replace_image(self, prop, index)
        elif action == "delete_image":
            delete_image(self, prop, index)

    def calc_price(self, price_table: dict) -> int | None:
        return price_table.get("price", {}).get(self.resolution, None)

    def start_check(self):
        """运行时检查"""
        pref = get_pref()
        if not Path(pref.output_cache_dir).exists():
            self.push_error(_T("Cache folder not find, please change..."))
            return False
        if pref.is_backup_mode:
            ...
        else:  # api模式
            ...
        return True

    def new_generate_task(self, account: "Account"):
        if self.is_task_submitting:
            print("有任务正在提交，请稍后")
            self.push_error(_T("Task is submitting, please wait..."))
            return
        if self.is_rendering:
            self.push_error(_T("Scene is rendering, please wait..."))
            return
        self.is_task_submitting = True
        if self.start_check():
            Thread(target=self.job, args=(account,), daemon=True).start()
        else:
            self.is_task_submitting = False

    def cancel_generate_task(self):
        self.task_manager.cancel_task(self.task_id)

    def job(self, account: "Account"):
        self.is_task_submitting = False
        # 1. 创建任务
        temp_folder = get_temp_folder(prefix="generate")
        temp_image_path = tempfile.NamedTemporaryFile(suffix=".png", prefix="Depth", delete=False, dir=temp_folder)
        _temp_image_path = temp_image_path.name
        # 渲染图片
        scene = bpy.context.scene
        if self.input_image_type == "CameraRender":
            if not bpy.context.scene.camera:
                self.push_error(_T("Scene Camera Not Found"))
                return
            render_agent = RenderAgent()
            self.is_rendering = True
            self.rendering_time_start = time.time()

            def on_write(_sce):
                if not check_image_valid(_temp_image_path):  # 渲染的图片错误
                    self.render_cancel = True

                self.is_rendering = False
                render_agent.detach()
                logger.info("on_write")

            render_agent.on_write(on_write)
            render_agent.attach()
            Timer.put((render_scene_to_png, scene, _temp_image_path))

            while self.is_rendering or self.render_cancel:
                time.sleep(0.5)
                if self.render_cancel:
                    self.push_error(_T("Render Canceled"))
                    self.render_cancel = False
                    return
        elif self.input_image_type == "CameraDepth":
            if not bpy.context.scene.camera:
                self.push_error(_T("Scene Camera Not Found"))
                return
            render_agent = RenderAgent()
            self.is_rendering = True
            self.rendering_time_start = time.time()

            def on_write(_sce):
                if not check_image_valid(_temp_image_path):  # 渲染的图片错误
                    self.render_cancel = True
                self.is_rendering = False
                render_agent.detach()
                logger.info("on_write")

            render_agent.on_write(on_write)
            render_agent.attach()
            Timer.put((render_scene_depth_to_png, scene, _temp_image_path))

            while self.is_rendering or self.render_cancel:
                time.sleep(0.5)
                if self.render_cancel:
                    self.push_error(_T("Render Canceled"))
                    self.render_cancel = False
                    return
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
            prompt = ""
            if not _temp_image_path:
                prompt += "所有图片均为参考图, "
            elif self.input_image_type == "CameraRender":
                prompt += "第一张图是渲染图(原图)，其他为参考图, "
            elif self.input_image_type == "CameraDepth":
                prompt += "第一张图是深度图，其他为参考图, "
            prompt += self.prompt
        task_type_map = {
            AuthMode.ACCOUNT.value: AccountGeminiImageGenerateTask,
            AuthMode.API.value: GeminiImageGenerationTask,
        }
        TaskType = task_type_map[account.auth_mode]
        api_key = self.api_key if account.auth_mode == AuthMode.API.value else account.token
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
            logger.info(f"渲染到：{_temp_image_path}")

        # 2. 注册回调
        def on_state_changed(event_data):
            _task: Task = event_data["task"]
            old_state: TaskState = event_data["old_state"]
            new_state: TaskState = event_data["new_state"]
            logger.info(f"状态改变: {old_state.value} -> {new_state.value}")

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
            logger.info(f"进度: {percent * 100}% - {message}")

        def on_completed(event_data):
            # result_data = {
            #     "image_data": b"",
            #     "mime_type": "image/png",
            #     "width": 1024,
            #     "height": 1024,
            # }
            account.fetch_credits()
            _task: Task = event_data["task"]
            result: TaskResult = event_data["result"]
            result_data: dict = result.data
            # 存储结果
            timestamp = time.time()
            time_str = datetime.fromtimestamp(timestamp).strftime("%Y%m%d%H%M%S")
            save_file = Path(temp_folder, f"Gen_{time_str}.png")
            save_file.write_bytes(result_data["image_data"])

            def load_image_into_blender(file_path: str):
                try:
                    bpy.data.images.load(file_path)
                except Exception:
                    print_exc()

            Timer.put((load_image_into_blender, save_file.as_posix()))
            logger.info(f"任务完成: {_task.task_id}")
            logger.info(f"结果已保存到: {save_file.as_posix()}")
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
                    logger.info(f"任务已取消: {_task.task_id}")
            except Exception:
                pass

        def on_failed(event_data):
            _task: Task = event_data["task"]
            result: TaskResult = event_data["result"]
            if not result.success:
                self.push_error(result.error)
                print(result.error)
                logger.debug(f"任务失败: {_task.task_id}")
            account.fetch_credits()

        task.register_callback("state_changed", on_state_changed)
        task.register_callback("progress_updated", on_progress)
        task.register_callback("completed", on_completed)
        task.register_callback("cancelled", on_cancelled)
        task.register_callback("failed", on_failed)
        logger.info(f"任务提交: {task.task_id}")

        # 3. 提交到管理器
        self.task_id = self.task_manager.submit_task(task)


def upload_image(client: StudioClient, prop: str):
    def upload_image_callback(files_path: [str]):
        # TODO 参考图片数量有限制,需要处理
        l = client.get_value(prop)
        for file_path in files_path:
            if file_path not in l:
                l.append(file_path)
        client.get_value(prop)[:] = client.get_value(prop)[:10]

    from ..ops import FileCallbackRegistry

    callback_id = FileCallbackRegistry.register_callback(upload_image_callback)
    bpy.ops.bas.file_importer("INVOKE_DEFAULT", callback_id=callback_id)


def replace_image(client: StudioClient, prop: str, index: int = -1):
    def replace_image_callback(files_path: [str]):
        if len(files_path) >= 1:
            file_path = files_path[0]
            try:
                client.get_value(prop)[index] = file_path
            except IndexError:
                client.get_value(prop).append(file_path)

    from ..ops import FileCallbackRegistry

    callback_id = FileCallbackRegistry.register_callback(replace_image_callback)
    bpy.ops.bas.file_importer("INVOKE_DEFAULT", callback_id=callback_id)


def delete_image(client: StudioClient, prop: str, index: int):
    client.get_value(prop).pop(index)
