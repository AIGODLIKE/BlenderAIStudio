import logging
from bpy.app.translations import pgettext as _T
from typing import Dict, Type
from .base import RequestBuilder
try:
    from ....logger import logger
except ImportError:
    logger = logging.getLogger("[BuilderRegistry]")


class BuilderRegistry:
    """请求构建器注册表（单例）

    负责注册和获取请求构建器实例。
    """

    _builders: Dict[str, Type[RequestBuilder]] = {}
    _instances: Dict[str, RequestBuilder] = {}

    @classmethod
    def register(cls, name: str, builder_class: Type[RequestBuilder]) -> None:
        """注册一个构建器类

        Args:
            name: 构建器名称（与配置文件中的 request_builder 字段对应）
            builder_class: 构建器类（继承自 RequestBuilder）
        """

        cls._builders[name] = builder_class
        logger.info(f"Registered builder: {name}")

    @classmethod
    def get(cls, name: str) -> RequestBuilder:
        """获取构建器实例（单例）

        Args:
            name: 构建器名称

        Returns:
            RequestBuilder 实例

        Raises:
            ValueError: 构建器未注册
        """
        if name not in cls._builders:
            raise ValueError(_T("Builder '{name}' not registered.").format(name=name))

        # 使用单例模式，每个构建器只创建一次
        if name not in cls._instances:
            cls._instances[name] = cls._builders[name]()

        return cls._instances[name]

    @classmethod
    def list_builders(cls) -> list[str]:
        """列出所有已注册的构建器名称"""
        return list(cls._builders.keys())

    @classmethod
    def has_builder(cls, name: str) -> bool:
        """检查构建器是否已注册"""
        return name in cls._builders
