from .base import ToolState
from .edit_image_tool import EditImageTool
from .extract_lineart_tool import ExtractLineartTool
from .prompt_reverse_tool import PromptReverseTool
from .registry import ImageToolRegistry
from .remove_background_tool import RemoveBackgroundTool

__all__ = [
    "ImageToolRegistry",
    "ToolState",
    "PromptReverseTool",
    "RemoveBackgroundTool",
    "ExtractLineartTool",
    "EditImageTool",
]


def register_default_tools():
    """按菜单顺序注册所有默认工具"""
    ImageToolRegistry.register(PromptReverseTool())
    ImageToolRegistry.register(RemoveBackgroundTool())
    ImageToolRegistry.register(ExtractLineartTool())
    # ImageToolRegistry.register(EditImageTool())


register_default_tools()
