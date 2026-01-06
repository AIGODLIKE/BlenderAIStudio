from abc import ABC, abstractmethod
from typing import Optional, Callable


class IMEManager(ABC):
    """输入法管理器抽象基类"""

    def __init__(self):
        self.composition_string = ""
        self.composition_callback: Optional[Callable] = None
        self.commit_callback: Optional[Callable] = None

    @abstractmethod
    def enable_ime(self) -> bool:
        """启用输入法"""
        pass

    @abstractmethod
    def disable_ime(self) -> bool:
        """禁用输入法"""
        pass

    def set_commit_callback(self, callback):
        """设置输入回调函数"""
        pass

    def refresh_input_method(self):
        """刷新输入法状态"""
        pass

    @abstractmethod
    def get_composition_string(self) -> str:
        """获取当前组字串"""
        pass

    def get_result_string(self) -> str:
        """获取当前结果串"""
        pass

    @abstractmethod
    def set_composition_position(self, x: int, y: int):
        """设置候选窗口位置"""
        pass
