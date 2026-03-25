import bpy
from bpy.app.translations import pgettext_iface as iface
from typing import TYPE_CHECKING, Optional

from .base import ImageTool, ToolState
from ...utils import get_pref

try:
    from ...logger import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from ..studio import StudioWrapper, AIStudio


MODEL_NAME = "NanoBanana2"


class ExtractLineartTool(ImageTool):
    """对参考图提取线稿，结果追加到参考图列表"""

    _running: dict[str, bool] = {}

    @property
    def name(self) -> str:
        return "extract_lineart"

    @property
    def display_name(self) -> str:
        return "ControlNet"

    @property
    def title(self) -> str:
        return "ControlNet视觉解构"

    @property
    def category(self) -> str:
        return "视觉分析"

    def cost(self, app: "AIStudio") -> str:
        resolution = app.client_wrapper.get_resolution()
        price = app.calc_model_price(MODEL_NAME, resolution)
        return str(price)

    @property
    def category_color(self) -> tuple:
        return (255 / 255, 195 / 255, 0 / 255, 1.0)

    @property
    def icon(self) -> Optional[str]:
        return "image_tools/image_line_art"

    @property
    def tooltips(self) -> list[str]:
        return [
            "消耗3积分",
            "从当前参考图中分离出线稿、色彩与空间深度信息",
            "并添加到当前图像列表",
        ]

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
            app.push_info_message(iface("Line art is already running"))
            return

        self._running[model_name] = True

        client = app.client
        config = client.get_meta("reference_images") if client else {}
        limit = config.get("limit") or 10

        prompt = get_pref().line_art_prompt
        original_model = client.current_model_name
        client.current_model_name = MODEL_NAME
        resolution = app.client_wrapper.get_resolution()
        item, task = client.add_line_art_task(
            prompt,
            app.state,
            reference_images=[image_path],
            resolution=resolution,
        )
        client.current_model_name = original_model

        def _poll_job():
            if not item.is_finished():
                return 1.0
            self._running[model_name] = False
            result_path = item.get_output_file_image()
            if result_path:
                images.append(result_path)
                images[:] = images[:limit]
            else:
                logger.error("ExtractLineartTool: 线稿结果为空")
                app.push_error_message("线稿结果为空, 请查看控制台日志, 并与开发者联系")

        bpy.app.timers.register(_poll_job)
