from .base import RequestBuilder, RequestData
from .registry import BuilderRegistry
from .gemini_builder import GeminiImageGenerateBuilder
from .seedream_builder import SeedreamImageGenerateBuilder

# 自动注册所有构建器
BuilderRegistry.register("GeminiImageGenerateBuilder", GeminiImageGenerateBuilder)
BuilderRegistry.register("SeedreamImageGenerateBuilder", SeedreamImageGenerateBuilder)
__all__ = [
    "RequestBuilder",
    "RequestData",
    "BuilderRegistry",
    "GeminiImageGenerateBuilder",
    "SeedreamImageGenerateBuilder",
]
