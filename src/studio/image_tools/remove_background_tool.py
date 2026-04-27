import bpy

from typing import TYPE_CHECKING

from .base import ImageTool, ToolState
from ...utils.image_processor import ImageProcessor

if TYPE_CHECKING:
    from ..studio import StudioWrapper, AIStudio


class RemoveBackgroundTool(ImageTool):
    """去背景工具 - 移除背景(万物抠图)"""

    _running: dict[str, bool] = {}

    @property
    def name(self) -> str:
        return "remove_background"

    @property
    def display_name(self) -> str:
        return "移除背景"

    @property
    def title(self) -> str:
        return "移除背景 (万物抠图)"

    @property
    def category(self) -> str:
        return "抠图"

    def cost(self, app: "AIStudio") -> str:
        return "3"

    @property
    def category_color(self) -> tuple[float, float, float, float]:
        return (67 / 255, 207 / 255, 124 / 255, 1.0)

    @property
    def icon(self) -> str | None:
        return "image_tools/remove_background"

    def tooltips(self, app: "AIStudio") -> list[str]:
        return [
            "消耗3积分",
            "AI 自动识别并去除图片背景",
            "支持人物、物品、产品等多种场景",
        ]

    @property
    def enabled(self) -> bool:
        return True

    def get_state(self, wrapper: "StudioWrapper") -> ToolState:
        if self._running.get(wrapper.model_name, False):
            return ToolState.RUNNING
        return ToolState.IDLE

    def execute(
        self,
        image_path: str,
        image_index: int,
        images: list[str],
        app: "AIStudio",
    ) -> None:
        model_name = app.client.model_name
        if self._running.get(model_name, False):
            app.push_info_message("Remove background is already running")
            return

        self._running[model_name] = True

        # 压缩图片
        image_path = ImageProcessor.compress_image_to_tempfile(image_path)
        if not image_path:
            app.push_info_message("Failed to compress image")
            self._running[model_name] = False
            return
        client = app.client
        account = app.state
        old_model_name = client.current_model_name
        client.current_model_name = "API"
        item, _task = client.add_remove_background_task(image_path, account)
        client.current_model_name = old_model_name

        def _poll_job():
            if item and not item.is_finished():
                return 1.0
            self._running[model_name] = False

        bpy.app.timers.register(_poll_job)
