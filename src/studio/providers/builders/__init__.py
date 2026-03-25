from .base import RequestBuilder, RequestData
from .registry import BuilderRegistry
from .gemini_builder import GeminiImageGenerateBuilder
from .seedream_builder import SeedreamImageGenerateBuilder
from .api_builder import APIBuilder

# 自动注册所有构建器
BuilderRegistry.register("GeminiImageGenerateBuilder", GeminiImageGenerateBuilder)
BuilderRegistry.register("GeminiImageGenerateBuilderPro", lambda: GeminiImageGenerateBuilder(is_pro=True))
BuilderRegistry.register("SeedreamImageGenerateBuilder", SeedreamImageGenerateBuilder)
BuilderRegistry.register("APIBuilder", APIBuilder)

__all__ = [
    "RequestBuilder",
    "RequestData",
    "BuilderRegistry",
    "GeminiImageGenerateBuilder",
    "SeedreamImageGenerateBuilder",
    "APIBuilder",
]
