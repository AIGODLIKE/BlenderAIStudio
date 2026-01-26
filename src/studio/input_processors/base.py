from abc import ABC, abstractmethod
from typing import Dict, Any


class InputProcessor(ABC):
    """输入处理器抽象基类

    所有输入处理器必须继承此类并实现以下方法：
    - process(): 处理输入数据
    - cancel(): 取消处理
    - cleanup(): 清理资源

    设计原则：
    - 单一职责：只处理输入数据的获取和转换
    - 可取消：支持任务取消
    - 无状态：每次调用 process() 都是独立的（除了取消标志）
    """

    @abstractmethod
    def process(self, params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """处理输入数据

        从 params 中提取输入配置参数，执行必要的处理（如渲染、加载文件等），
        返回处理结果（如 image_path）。

        Args:
            params: 输入参数字典
            context: Blender 上下文信息

        Returns:
            处理结果字典

        Raises:
            ValueError: 参数无效或缺失
            RuntimeError: 处理失败（如渲染失败）
            CancelledError: 处理被取消
        """
        pass

    @abstractmethod
    def cancel(self) -> None:
        """取消输入处理

        设置取消标志，正在进行的处理应尽快退出。
        """
        pass

    @abstractmethod
    def cleanup(self) -> None:
        """清理资源

        释放处理器使用的资源，如：
        - 临时文件
        - 网络连接
        - 内存缓存
        """
        pass


class CancelledError(Exception):
    """处理被取消异常

    当 InputProcessor 检测到取消标志时，应该抛出此异常。
    """

    pass
