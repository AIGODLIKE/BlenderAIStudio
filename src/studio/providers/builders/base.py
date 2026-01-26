from abc import ABC, abstractmethod
from typing import Dict, Any, TYPE_CHECKING
from dataclasses import dataclass, field

if TYPE_CHECKING:
    from ...config.model_registry import ModelConfig


@dataclass
class RequestData:
    """HTTP 请求数据"""

    url: str
    headers: Dict[str, str]
    payload: Dict[str, Any]
    method: str = "POST"
    query_params: Dict[str, str] = field(default_factory=dict)
    timeout: int = 300


class RequestBuilder(ABC):
    """请求构建器抽象基类

    所有请求构建器必须继承此类并实现 build 方法。
    负责构建完整的 HTTP 请求，包括 URL、Headers、Payload 等。
    """

    @abstractmethod
    def build(self, params: Dict[str, Any], model_config: "ModelConfig", auth_mode: str, credentials: Dict[str, str]) -> RequestData:
        """构建完整的 HTTP 请求

        Args:
            params: 用户提供的参数字典（已由 InputProcessor 处理）
                   例如：{"prompt": "...", "image_path": "/tmp/render.png", "size_config": "16:9"}
            model_config: 模型配置对象
            auth_mode: 认证模式
            credentials: 认证凭证（如 {"api_key": "xxx"}）

        Returns:
            RequestData 对象，包含完整的请求信息

        Raises:
            ValueError: 参数不合法
        """
        pass
