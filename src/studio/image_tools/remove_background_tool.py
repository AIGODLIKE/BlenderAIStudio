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
        return "去背景"

    @property
    def icon(self) -> Optional[str]:
        return "image_screenshot"

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
