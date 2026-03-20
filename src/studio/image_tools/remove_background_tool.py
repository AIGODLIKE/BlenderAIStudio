from typing import TYPE_CHECKING, Optional

from .base import ImageTool

if TYPE_CHECKING:
    from ..studio import StudioWrapper, AIStudio


class RemoveBackgroundTool(ImageTool):
    """去背景工具（占位，暂无实际功能）"""

    @property
    def name(self) -> str:
        return "remove_background"

    @property
    def display_name(self) -> str:
        return "移除背景"

    @property
    def category(self) -> str:
        return "抠图"

    @property
    def cost(self) -> int:
        return 3

    @property
    def category_color(self) -> tuple:
        return (67 / 255, 207 / 255, 124 / 255, 1.0)

    @property
    def icon(self) -> Optional[str]:
        return "image_tools/remove_background"

    @property
    def tooltips(self) -> list[str]:
        return ["去除参考图背景 (即将推出)"]

    @property
    def enabled(self) -> bool:
        return False

    def execute(
        self,
        image_path: str,
        image_index: int,
        images: list[str],
        wrapper: "StudioWrapper",
        app: "AIStudio",
    ) -> None:
        pass
