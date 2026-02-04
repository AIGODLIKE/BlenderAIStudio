import logging
from typing import Dict, Type, Union, Callable
from .base import ResponseParser

try:
    from ....logger import logger
except ImportError:
    logger = logging.getLogger("[ParserRegistry]")


class ParserRegistry:
    """响应解析器注册表（单例）

    负责注册和获取响应解析器实例。
    """

    _parsers: Dict[str, Union[Type[ResponseParser], Callable[[], ResponseParser]]] = {}
    _instances: Dict[str, ResponseParser] = {}

    @classmethod
    def register(cls, name: str, parser_class: Union[Type[ResponseParser], Callable[[], ResponseParser]]) -> None:
        """注册一个解析器类或工厂函数

        Args:
            name: 解析器名称（与配置文件中的 response_parser 字段对应）
            parser_class: 解析器类（继承自 ResponseParser）或工厂函数

        Raises:
            TypeError: 如果 parser_class 不是 ResponseParser 的子类或可调用对象
        """
        # 支持类或工厂函数
        if not (callable(parser_class) or (isinstance(parser_class, type) and issubclass(parser_class, ResponseParser))):
            raise TypeError(f"{parser_class} must be a subclass of ResponseParser or a callable factory")

        cls._parsers[name] = parser_class
        logger.info(f"Registered parser: {name}")

    @classmethod
    def get(cls, name: str) -> ResponseParser:
        """获取解析器实例（单例）

        Args:
            name: 解析器名称

        Returns:
            ResponseParser 实例

        Raises:
            ValueError: 如果解析器未注册
        """
        if name not in cls._parsers:
            available = ", ".join(cls._parsers.keys())
            raise ValueError(f"Parser '{name}' not registered. Available parsers: {available or 'None'}")

        # 使用单例模式，每个解析器只创建一次
        if name not in cls._instances:
            parser_factory = cls._parsers[name]
            # 如果是工厂函数，直接调用；否则实例化类
            if isinstance(parser_factory, type):
                cls._instances[name] = parser_factory()
            else:
                cls._instances[name] = parser_factory()

        return cls._instances[name]

    @classmethod
    def list_parsers(cls) -> list[str]:
        """列出所有已注册的解析器名称"""
        return list(cls._parsers.keys())

    @classmethod
    def has_parser(cls, name: str) -> bool:
        """检查解析器是否已注册"""
        return name in cls._parsers
