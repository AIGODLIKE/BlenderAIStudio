import base64

from pathlib import Path
from typing import Any, TYPE_CHECKING

from bpy.app.translations import pgettext as _T

from .base import RequestBuilder, RequestData

if TYPE_CHECKING:
    from ...config.model_registry import ModelConfig


class PromptReverseBuilder(RequestBuilder):
    def build(
        self,
        params: dict[str, Any],
        model_config: "ModelConfig",
        auth_mode: str,
        credentials: dict[str, str],
    ) -> RequestData:
        # 获取功能类型
        action: str = params.get("__action", model_config.default_action)

        # 验证功能支持
        if not model_config.supports_action(action):
            error_msg: str = _T("Action '{action}' not supported for model 'API'.") or ""
            error_msg = error_msg.format(action=action, model_name=model_config.model_name)
            raise ValueError(error_msg)

        # 构建 URL
        url = model_config.build_api_url(auth_mode)

        # 构建 Headers
        endpoint = model_config.get_endpoint(auth_mode)
        headers = self._build_headers(endpoint["headers"], credentials)

        payload = self._build_payload(params)
        task_id = credentials.get("reqId", "")
        payload["reqId"] = task_id

        # 返回完整请求数据
        return RequestData(
            url=url,
            headers=headers,
            payload=payload,
            method=endpoint.get("method", "POST"),
            timeout=80,
        )

    def _build_headers(
        self,
        header_template: dict[str, str],
        credentials: dict[str, str],
    ) -> dict[str, str]:
        headers: dict[str, str] = {}

        for key, value in header_template.items():
            if isinstance(value, str) and "{" in value:
                # 替换认证凭证占位符
                for cred_key, cred_value in credentials.items():
                    value = value.replace(f"{{{cred_key}}}", cred_value)
            headers[key] = value

        return headers

    def _build_payload(self, params: dict[str, Any]) -> dict[str, Any]:
        ref_images_path = params.get("reference_images", [])
        prompt = params.get("prompt", "")

        # 20MB
        total_image_size_limit = 20 * 1024 * 1024
        total_image_size = 0

        for _image_path in ref_images_path:
            total_image_size += Path(_image_path).stat().st_size
        if total_image_size > total_image_size_limit:
            raise ValueError("Total image size exceeds the limit of 20MB.")

        payload = {"imageBase64": ""}

        if prompt:
            payload["prompt"] = prompt

        for reference_image_path in ref_images_path:
            with open(reference_image_path, "rb") as f:
                image_base64 = base64.b64encode(f.read()).decode("utf-8")
                payload["imageBase64"] = image_base64
            break

        return payload
