from typing import Dict, Type
from .base import InputProcessor


class InputProcessorRegistry:
    """InputProcessor 注册表

    单例模式的注册表，用于管理所有可用的 InputProcessor。

    职责：
    - 注册 InputProcessor 类
    - 根据名称获取 InputProcessor 实例
    - 列出所有已注册的处理器

    使用场景：
    - 配置文件中通过名称引用处理器
    - 动态创建处理器实例
    - 扩展支持新的输入源
    """

    # 类变量：存储所有已注册的处理器类
    _processors: Dict[str, Type[InputProcessor]] = {}

    @classmethod
    def register(cls, name: str, processor_class: Type[InputProcessor]) -> None:
        """注册一个输入处理器类

        Args:
            name: 处理器名称（与配置文件中的 processor 字段对应）
                 建议使用类名，如 "RenderProcessor"
            processor_class: 处理器类（必须继承自 InputProcessor）

        Raises:
            ValueError: 如果 name 已经被注册
        """
        # 检查重复注册
        if name in cls._processors:
            existing_class = cls._processors[name]
            reg_name = existing_class.__name__
            if existing_class != processor_class:
                raise ValueError(f"Processor '{name}' is already registered with class {reg_name}")

        # 注册
        cls._processors[name] = processor_class

    @classmethod
    def get(cls, name: str) -> InputProcessor:
        """获取输入处理器实例

        根据名称创建并返回一个新的处理器实例。

        Args:
            name: 处理器名称

        Returns:
            InputProcessor 实例

        Raises:
            ValueError: 如果处理器未注册
        """
        if name not in cls._processors:
            available = ", ".join(cls._processors.keys()) or "None"
            raise ValueError(f"InputProcessor '{name}' not registered. Available processors: {available}")

        # 创建新实例
        processor_class = cls._processors[name]
        return processor_class()

    @classmethod
    def is_registered(cls, name: str) -> bool:
        """检查处理器是否已注册

        Args:
            name: 处理器名称

        Returns:
            bool: True 表示已注册，False 表示未注册
        """
        return name in cls._processors

    @classmethod
    def list_all(cls) -> list:
        """列出所有已注册的处理器名称

        Returns:
            list: 处理器名称列表
        """
        return list(cls._processors.keys())

    @classmethod
    def unregister(cls, name: str) -> None:
        """注销一个处理器（主要用于测试）

        Args:
            name: 处理器名称
        """
        cls._processors.pop(name, None)

    @classmethod
    def clear(cls) -> None:
        """清空所有已注册的处理器（主要用于测试）"""
        cls._processors.clear()
