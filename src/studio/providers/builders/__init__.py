from .base import RequestBuilder, RequestData
from .registry import BuilderRegistry
from .gemini_builder import GeminiImageGenerateBuilder

# 自动注册所有构建器
BuilderRegistry.register("GeminiImageGenerateBuilder", GeminiImageGenerateBuilder)

__all__ = [
    "RequestBuilder",
    "RequestData",
    "BuilderRegistry",
]
