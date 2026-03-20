from typing import TYPE_CHECKING, Optional

from .base import ImageTool
from .edit_text_panel import EditTextPanel

if TYPE_CHECKING:
    from ..studio import StudioWrapper, AIStudio


class EditImageTool(ImageTool):
    """编辑图片中的文字：OCR 识别后逐行编辑替换"""

    _panel: EditTextPanel = EditTextPanel()

    @property
    def name(self) -> str:
        return "edit_image"

    @property
    def display_name(self) -> str:
        return "编辑文本"

    @property
    def category(self) -> str:
        return "编辑"

    @property
    def cost(self) -> int:
        return 3

    @property
    def category_color(self) -> tuple[float, float, float, float]:
        return (42 / 255, 130 / 255, 228 / 255, 1.0)

    @property
    def icon(self) -> Optional[str]:
        return "image_tools/edit_text"

    @property
    def tooltips(self) -> list[str]:
        return [
            "识别图像中的文字并逐行编辑替换",
            "支持 OCR 自动识别或手动粘贴",
        ]

    @property
    def enabled(self) -> bool:
        return True

    def execute(
        self,
        image_path: str,
        image_index: int,
        images: list[str],
        wrapper: "StudioWrapper",
        app: "AIStudio",
    ) -> None:
        self._panel.open(image_path)

    def draw_panel(self, app: "AIStudio"):
        self._panel.draw(app)
