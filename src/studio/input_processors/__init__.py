from .base import InputProcessor, CancelledError
from .registry import InputProcessorRegistry
from .blender_render import RenderProcessor

# 注册内置处理器
InputProcessorRegistry.register("RenderProcessor", RenderProcessor)

__all__ = [
    "InputProcessor",
    "CancelledError",
    "InputProcessorRegistry",
    "RenderProcessor",
]
