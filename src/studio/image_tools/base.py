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
        """菜单显示名称"""

    @property
    def icon(self) -> Optional[str]:
        return None

    @property
    def tooltips(self) -> list[str]:
        """tooltip 提示信息行列表"""
        return []

    @property
    def enabled(self) -> bool:
        """是否可用（False 时菜单项灰显）"""
        return True

    @abstractmethod
    def execute(
        self,
        image_path: str,
        image_index: int,
        images: list[str],
        wrapper: "StudioWrapper",
        app: "AIStudio",
    ) -> None:
        """执行工具操作

        Args:
            image_path: 参考图文件路径
            image_index: 参考图在列表中的索引
            images: 参考图列表引用（用于追加结果等）
            wrapper: Studio wrapper 实例
            app: AIStudio 实例
        """

    def get_state(self, wrapper: "StudioWrapper") -> ToolState:
        return ToolState.IDLE
