import bpy

from typing import TYPE_CHECKING
from typing_extensions import override

from .base import ImageTool, ToolState

if TYPE_CHECKING:
    from ..studio import StudioWrapper, AIStudio


class RemoveBackgroundTool(ImageTool):
    """去背景工具 - 移除背景(万物抠图)"""

    _running: dict[str, bool] = {}

    @property
    @override
    def name(self) -> str:
        return "remove_background"

    @property
    @override
    def display_name(self) -> str:
        return "移除背景"

    @property
    @override
    def title(self) -> str:
        return "移除背景 (万物抠图)"

    @property
    @override
    def category(self) -> str:
        return "抠图"

    @property
    @override
    def cost(self) -> int:
        return 3

    @property
    @override
    def category_color(self) -> tuple[float, float, float, float]:
        return (67 / 255, 207 / 255, 124 / 255, 1.0)

    @property
    @override
    def icon(self) -> str | None:
        return "image_tools/remove_background"

    @property
    @override
    def tooltips(self) -> list[str]:
        return [
            "消耗积分",
            "AI 自动识别并去除图片背景",
            "支持人物、物品、产品等多种场景",
        ]

    @property
    @override
    def enabled(self) -> bool:
        return True

    @override
    def get_state(self, wrapper: "StudioWrapper") -> ToolState:
        if self._running.get(wrapper.model_name, False):
            return ToolState.RUNNING
        return ToolState.IDLE

    @override
    def execute(
        self,
        image_path: str,
        image_index: int,
        images: list[str],
        wrapper: "StudioWrapper",
        app: "AIStudio",
    ) -> None:
        model_name = wrapper.model_name
        if self._running.get(model_name, False):
            app.push_info_message("Remove background is already running")
            return

        self._running[model_name] = True

        client = wrapper.studio_client
        account = app.state

        item, _task = client.add_remove_background_task(image_path, account)

        def _poll_job():
            if item and not item.is_finished():
                return 1.0
            self._running[model_name] = False

        bpy.app.timers.register(_poll_job)
