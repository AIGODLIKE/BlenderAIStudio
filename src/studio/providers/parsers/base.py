from abc import ABC, abstractmethod
from typing import Any
import requests


class ResponseParser(ABC):
    """响应解析器抽象基类

    所有响应解析器必须继承此类并实现以下方法：
    - parse(): 解析响应数据
    - _check_response(): 检查响应是否有错误

    不同的 API 提供商可以有不同的错误检查逻辑。
    """

    @abstractmethod
    def parse(self, response: requests.Response) -> list[tuple[str, Any]]:
        """解析 HTTP 响应

        此方法应该：
        1. 检查响应状态
        2. 从响应中提取数据
        3. 转换为适当的格式

        Args:
            response: requests.Response 对象

        Returns:
            list[tuple[str, Any]]: 解析后的数据，类型取决于具体的 Parser：
                - 图像模型：Tuple[str, bytes] (mime_type, image_data)
                - 音频模型：Tuple[str, bytes] (mime_type, audio_data)
                - 视频模型：Tuple[str, bytes] (mime_type, video_data)
                - 文本模型：Tuple[str, str]   (mime_type, text_data)

        Raises:
            Exception: 解析失败时抛出异常
        """
        pass

    def _check_response(self, response: requests.Response) -> None:
        """检查 HTTP 响应是否包含错误

        此方法应该检查：
        1. HTTP 状态码
        2. 响应体中的错误信息（不同 API 格式不同）

        默认实现只检查 HTTP 状态码，子类可以重写以添加自定义检查。

        Args:
            response: requests.Response 对象

        Raises:
            requests.HTTPError: HTTP 状态码错误
            ValueError: 响应体包含错误信息
            Exception: 其他错误
        """
        # 默认实现：只检查 HTTP 状态码
        try:
            response.raise_for_status()
        except requests.HTTPError as e:
            # 尝试提取错误信息
            error_msg = f"HTTP {response.status_code}: {response.reason}"
            try:
                error_data = response.json()
                if isinstance(error_data, dict):
                    error_msg += f" - {error_data}"
            except Exception:
                pass
            raise requests.HTTPError(error_msg, response=response) from e
