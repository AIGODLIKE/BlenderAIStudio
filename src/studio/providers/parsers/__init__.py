from .base import ResponseParser
from .registry import ParserRegistry
from .gemini_parser import GeminiImageParser

# 自动注册所有解析器
ParserRegistry.register("GeminiImageParser", GeminiImageParser)

# 注册账号模式的 Parser（使用 lambda 创建实例）
ParserRegistry.register("GeminiImageParserAccount", lambda: GeminiImageParser(is_account_mode=True))

__all__ = [
    "ResponseParser",
    "ParserRegistry",
]
