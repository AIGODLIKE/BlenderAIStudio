from bpy.app.translations import pgettext as _T
from typing import Dict, Any, TYPE_CHECKING
from .base import RequestBuilder, RequestData


if TYPE_CHECKING:
    from ...config.model_registry import ModelConfig


class SeedreamImageGenerateBuilder(RequestBuilder):
    def build(self, params: Dict[str, Any], model_config: "ModelConfig", auth_mode: str, credentials: Dict[str, str]) -> RequestData:
        action = params.get("__action", model_config.default_action)

        if not model_config.supports_action(action):
            error_msg: str = _T("Action '{action}' not supported for model '{model_name}'.")
            error_msg = error_msg.format(action=action, model_name=model_config.model_name)
            raise ValueError(error_msg)

        url = model_config.build_api_url(auth_mode)

        endpoint = model_config.get_endpoint(auth_mode)
        headers = self._build_headers(
            endpoint["headers"],
            credentials,
            model_config,
            params,
        )

        if action == "generate":
            payload = self._build_generate_payload(params)
        elif action == "edit":
            payload = self._build_edit_payload(params)
        else:
            raise ValueError(_T("Unknown action: '{action}'.").format(action=action))

        return RequestData(
            url=url,
            headers=headers,
            payload=payload,
            method=endpoint.get("method", "POST"),
            timeout=300,
        )

    def _build_headers(
        self,
        header_template: Dict[str, str],
        credentials: Dict[str, str],
        model_config: "ModelConfig",
        params: Dict[str, Any],
    ) -> Dict[str, str]:
        headers = {}

        for key, value in header_template.items():
            if isinstance(value, str) and "{" in value:
                # 替换认证凭证占位符
                for cred_key, cred_value in credentials.items():
                    value = value.replace(f"{{{cred_key}}}", cred_value)

                # 特殊占位符替换
                if "{size}" in value:
                    value = value.replace("{size}", params.get("resolution", "1K"))

            headers[key] = value

        return headers

    def _build_generate_payload(self, params: Dict[str, Any]) -> dict:
        payload = {}
        return payload

    def _build_edit_payload(self, params: Dict[str, Any]) -> dict:
        payload = {}
        return payload
