from typing import TYPE_CHECKING, Optional

from .base import ImageTool

if TYPE_CHECKING:
    from ..studio import StudioWrapper, AIStudio


class EditImageTool(ImageTool):
    """编辑图片工具（占位，暂无实际功能）"""

    @property
    def name(self) -> str:
        return "edit_image"

    @property
    def display_name(self) -> str:
        return "编辑"

    @property
    def icon(self) -> Optional[str]:
        return "image_edit"

    @property
    def tooltips(self) -> list[str]:
        return ["编辑当前参考图 (即将推出)"]

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
