from .base import RequestBuilder, RequestData
from .registry import BuilderRegistry
from .gemini_builder import GeminiImageGenerateBuilder
from .seedream_builder import SeedreamImageGenerateBuilder
from .gpt_image_builder import GPTImageGenerateBuilder
from .api_builder import APIBuilder
from .v2_image_builder import V2ImageBuilder

# 自动注册所有构建器
BuilderRegistry.register("GeminiImageGenerateBuilder", GeminiImageGenerateBuilder)
BuilderRegistry.register("GeminiImageGenerateBuilderPro", lambda: GeminiImageGenerateBuilder(is_pro=True))
BuilderRegistry.register("SeedreamImageGenerateBuilder", SeedreamImageGenerateBuilder)
BuilderRegistry.register("GPTImageGenerateBuilder", GPTImageGenerateBuilder)
BuilderRegistry.register("APIBuilder", APIBuilder)

# V2 图像生成构建器（account 模式，委托内部 builder 构建 payload 后包装为 V2 格式）
BuilderRegistry.register("V2GeminiImageBuilder", lambda: V2ImageBuilder("GeminiImageGenerateBuilder"))
BuilderRegistry.register("V2GeminiImageBuilderPro", lambda: V2ImageBuilder("GeminiImageGenerateBuilderPro"))
BuilderRegistry.register("V2SeedreamImageBuilder", lambda: V2ImageBuilder("SeedreamImageGenerateBuilder"))
BuilderRegistry.register("V2GPTImageBuilder", lambda: V2ImageBuilder("GPTImageGenerateBuilder"))

__all__ = [
    "RequestBuilder",
    "RequestData",
    "BuilderRegistry",
    "GeminiImageGenerateBuilder",
    "SeedreamImageGenerateBuilder",
    "GPTImageGenerateBuilder",
    "APIBuilder",
    "V2ImageBuilder",
]
