from .base import ResponseParser
from .registry import ParserRegistry
from .gemini_parser import GeminiImageParser
from .seedream_parser import SeedreamImageParser
from .gpt_image_parser import GPTImageParser
from .api_parser import APIParser
from .v2_image_parser import V2ImageParser

# 自动注册所有解析器
ParserRegistry.register("GeminiImageParser", GeminiImageParser)
ParserRegistry.register("SeedreamImageParser", SeedreamImageParser)
ParserRegistry.register("GPTImageParser", GPTImageParser)
ParserRegistry.register("APIParser", APIParser)
# 注册账号模式的 Parser（使用 lambda 创建实例）
ParserRegistry.register("GeminiImageParserAccount", lambda: GeminiImageParser(is_account_mode=True))
ParserRegistry.register("SeedreamImageParserAccount", lambda: SeedreamImageParser(is_account_mode=True))
# V2 图像生成解析器（account 模式异步提交）
ParserRegistry.register("V2ImageParser", V2ImageParser)

__all__ = [
    "ResponseParser",
    "ParserRegistry",
    "GeminiImageParser",
    "SeedreamImageParser",
    "GPTImageParser",
    "APIParser",
    "V2ImageParser",
]
