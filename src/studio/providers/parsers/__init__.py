from .base import ResponseParser
from .registry import ParserRegistry
from .gemini_parser import GeminiImageParser
from .seedream_parser import SeedreamImageParser
from .api_parser import APIParser

# 自动注册所有解析器
ParserRegistry.register("GeminiImageParser", GeminiImageParser)
ParserRegistry.register("SeedreamImageParser", SeedreamImageParser)
ParserRegistry.register("APIParser", APIParser)
# 注册账号模式的 Parser（使用 lambda 创建实例）
ParserRegistry.register("GeminiImageParserAccount", lambda: GeminiImageParser(is_account_mode=True))
ParserRegistry.register("SeedreamImageParserAccount", lambda: SeedreamImageParser(is_account_mode=True))

__all__ = [
    "ResponseParser",
    "ParserRegistry",
    "GeminiImageParser",
    "SeedreamImageParser",
    "APIParser",
]
