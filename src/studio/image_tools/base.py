from abc import ABC, abstractmethod
from enum import Enum
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ..studio import StudioWrapper, AIStudio


class ToolState(Enum):
    IDLE = "idle"
    RUNNING = "running"


class ImageTool(ABC):
    """参考图右键菜单工具的抽象基类

    每个工具代表一项可对参考图执行的操作（如反求提示词、提取线稿等）。
    工具通过 ImageToolRegistry 注册后，由右键菜单统一驱动。
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """工具唯一标识"""

    @property
    @abstractmethod
    def display_name(self) -> str:
        """菜单行显示名称"""

    @property
    def title(self) -> str:
        """工具标题（用于 tooltip 等场景），默认与 display_name 相同"""
        return self.display_name

    @property
    def icon(self) -> Optional[str]:
        return None

    def tooltips(self, app: "AIStudio") -> list[str]:
        """tooltip 提示信息行列表"""
        return []

    @property
    def enabled(self) -> bool:
        """是否可用（False 时菜单项灰显）"""
        return True

    @property
    def category(self) -> str:
        """工具分类名称（用于菜单分组显示）"""
        return ""

    def cost(self, app: "AIStudio") -> str:
        """工具消耗的积分数"""
        return "0"

    @property
    def category_color(self) -> tuple[float, float, float, float]:
        """分类指示条颜色 (r, g, b, a)"""
        return (1.0, 1.0, 1.0, 1.0)

    @abstractmethod
    def execute(
        self,
        image_path: str,
        image_index: int,
        images: list[str],
        app: "AIStudio",
    ) -> None:
        """执行工具操作

        Args:
            image_path: 参考图文件路径
            image_index: 参考图在列表中的索引
            images: 参考图列表引用（用于追加结果等）
            app: AIStudio 实例
        """

    def get_state(self, wrapper: "StudioWrapper") -> ToolState:
        return ToolState.IDLE

    def draw(self, app: "AIStudio"):
        pass