import requests
from typing import Dict, Any
from .base import BaseProvider
from .builders import BuilderRegistry
from .parsers import ParserRegistry
from ..config.model_registry import ModelConfig
from ..account import AuthMode


class UniversalProvider(BaseProvider):
    """通用 Provider

    根据模型配置动态加载对应的 Builder 和 Parser，
    实现统一的请求发送和响应处理。

    支持多种模态：
    - 图像（生成、编辑、风格迁移）
    - 音频（生成、转换、语音识别）
    - 视频（生成、编辑、转换）
    - 文本（生成、翻译、摘要）
    """

    def __init__(self, model_config: ModelConfig, auth_mode: str, credentials: Dict[str, str], task_id: str):
        """初始化通用 Provider

        Args:
            model_config: 模型配置对象
            auth_mode: 认证模式
            credentials: 认证凭证字典，如 {"api_key": "xxx"} 或 {"token": "xxx"}
            task_id: 任务ID

        Raises:
            ValueError: 如果认证模式不支持或 Builder/Parser 未注册
        """
        if not model_config.supports_auth_mode(auth_mode):
            raise ValueError(f"Model '{model_config.model_name}' not support auth mode '{auth_mode}'. ")

        self.model_config = model_config
        self.auth_mode = auth_mode
        self.credentials = credentials
        self.task_id = task_id

        # 动态加载构建器
        self.request_builder = self._get_builder(model_config.request_builder)

        # 动态加载觧析器（优先从 endpoint 配置中获取）
        endpoint = model_config.get_endpoint(auth_mode)
        parser_name = endpoint.get("response_parser") or model_config.response_parser
        self.response_parser = self._get_parser(parser_name)

    def _get_builder(self, builder_name: str):
        """从注册表获取构建器实例"""
        return BuilderRegistry.get(builder_name)

    def _get_parser(self, parser_name: str):
        """从注册表获取解析器实例"""
        return ParserRegistry.get(parser_name)

    def execute(self, params: Dict[str, Any]) -> Any:
        """执行模型请求（通用方法）

        这是一个通用的执行方法，适用于所有模态和功能：
        - 图像：生成、编辑、风格迁移
        - 音频：生成、转换、语音识别
        - 视频：生成、编辑、转换
        - 文本：生成、翻译、摘要

        Args:
            params: 参数字典，由用户提供，必须包含：
                - action: 功能类型（可选，默认使用 model_config.default_action）
                - 其他模型特定参数

        Returns:
            解析后的响应数据，类型由 ResponseParser 决定：
            - 图像模型：Tuple[str, bytes] (mime_type, image_data)
            - 音频模型：Tuple[str, bytes] (mime_type, audio_data)
            - 视频模型：Tuple[str, bytes] (mime_type, video_data)
            - 文本模型：Tuple[str, str]   (mime_type, text_data)

        Raises:
            requests.RequestException: 网络请求异常
            ValueError: 参数验证失败或 action 不支持
            Exception: 其他异常
        """
        # 1. 使用 Builder 构建完整请求
        request_data = self.request_builder.build(
            params=params,
            model_config=self.model_config,
            auth_mode=self.auth_mode,
            credentials=self.credentials,
        )

        # TODO 待改进(目前硬编码) 这里ID用于账户模式后端标识
        if self.auth_mode == AuthMode.ACCOUNT.value:
            request_data.query_params["reqId"] = self.task_id

        # 2. 发送 HTTP 请求
        response = requests.request(
            method=request_data.method,
            url=request_data.url,
            headers=request_data.headers,
            json=request_data.payload,
            params=request_data.query_params,
            timeout=request_data.timeout,
        )

        # 3. 解析响应数据
        return self.response_parser.parse(response)
