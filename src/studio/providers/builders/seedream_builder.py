from bpy.app.translations import pgettext as _T
import base64
from copy import deepcopy
from pathlib import Path
from typing import Dict, Any, TYPE_CHECKING, List
from .base import RequestBuilder, RequestData
from .seedream_prompt import (
    GENERATE_RENDER_WITH_REFERENCE,
    GENERATE_RENDER_WITHOUT_REFERENCE,
    GENERATE_DEPTH_MAP_WITHOUT_REFERENCE,
    GENERATE_DEPTH_MAP_WITH_REFERENCE,
    EDIT_SMART_REPAIR,
    EDIT_WITH_MASK_AND_REFERENCES,
    EDIT_WITH_MASK,
    EDIT_WITH_REFERENCES,
    EDIT_BASE_PROMPT,
)

if TYPE_CHECKING:
    from ...config.model_registry import ModelConfig


class SeedreamImageGenerateBuilder(RequestBuilder):
    def build(self, params: Dict[str, Any], model_config: "ModelConfig", auth_mode: str,
              credentials: Dict[str, str]) -> RequestData:
        params = self._preprocess_params(params)
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
            payload = self._build_generate_payload(params, model_config)
        elif action == "edit":
            payload = self._build_edit_payload(params, model_config)
        else:
            raise ValueError(_T("Unknown action: '{action}'.").format(action=action))

        return RequestData(
            url=url,
            headers=headers,
            payload=payload,
            method=endpoint.get("method", "POST"),
            timeout=80,
        )

    def _preprocess_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        processed = deepcopy(params)
        # 兼容上游字段：prompt / user_prompt
        if "prompt" not in processed and "user_prompt" in processed:
            processed["prompt"] = processed.get("user_prompt", "")
        if "__action" not in processed:
            processed["__action"] = "generate"
        return processed

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

    def _build_generate_payload(self, params: Dict[str, Any], model_config: "ModelConfig") -> dict:
        """
        参考 OpenAI Images API 的请求结构，并对齐 Seedream 文档字段：
        - model / prompt / size
        - image(可选): data:image/<fmt>;base64,<...> 列表
        """
        ref_images_path = params.get("reference_images", [])
        is_color_render = params.get("is_color_render", False)
        model = params.get("model") or model_config.model_id
        prompt = params.get("prompt", "").strip()
        full_prompt = self._build_generate_prompt(
            prompt,
            has_reference=bool(ref_images_path),
            is_color_render=is_color_render,
        )

        size = self._resolve_size(params)
        images = self._collect_images_as_data(params)

        payload: Dict[str, Any] = {
            "model": model,
            "prompt": full_prompt,
            "size": size,
            "image": images,
            "response_format": "b64_json",
            "watermark": False,
            "sequential_image_generation": "disabled",
        }
        return payload

    def _build_edit_payload(self, params: Dict[str, Any], model_config: "ModelConfig") -> dict:
        prompt = params.get("prompt", "").strip()
        ref_images_path = params.get("reference_images", [""])
        mask_image_path = ref_images_path[0] if ref_images_path else ""
        prompt = self._build_edit_prompt(
            prompt,
            has_mask=bool(mask_image_path),
            has_reference=bool(ref_images_path[1:]),
        )
        payload = self._build_generate_payload(params, model_config)
        payload["prompt"] = prompt

        return payload

    def _resolve_size(self, params: Dict[str, Any]) -> str:
        """
        Seedream 支持：
        - '1K'/'2K'/'4K'
        - 'WIDTHxHEIGHT'（如 2048x2048）
        工程里 UI 通常提供 resolution 字段。
        """
        size = params.get("size")
        if isinstance(size, str) and size.strip():
            return size.strip()

        # 兼容工程里常用的 resolution 选择
        resolution = params.get("resolution")
        if isinstance(resolution, str) and resolution.strip():
            return resolution.strip()

        # 兼容 width/height
        w = params.get("width")
        h = params.get("height")
        if isinstance(w, int) and isinstance(h, int) and w > 0 and h > 0:
            return f"{w}x{h}"

        return "1K"

    def _collect_images_as_data(self, params: Dict[str, Any]) -> List[str]:
        """
        收集可能的输入图片来源并编码为 data URL 列表：
        - params['image']  (str 或 list)
        - params['main_image'] / params['image_path']
        - params['reference_images'] (list)
        - params['mask_path']
        """

        def _as_list(v: Any) -> List[Any]:
            if v is None:
                return []
            if isinstance(v, list):
                return v
            return [v]

        candidates: List[Any] = []
        candidates += _as_list(params.get("image"))
        candidates += _as_list(params.get("main_image"))
        candidates += _as_list(params.get("image_path"))
        candidates += _as_list(params.get("mask_path"))
        candidates += _as_list(params.get("reference_images"))

        out: List[str] = []
        for item in candidates:
            if not item:
                continue

            if isinstance(item, (str, Path)):
                p = Path(item)
                if p.exists() and p.is_file():
                    out.append(self._file_to_data_url(p))
                    continue

        return out

    def _file_to_data_url(self, path: Path) -> str:
        ext = path.suffix.lower().lstrip(".")
        if ext in {"jpg", "jpeg"}:
            fmt = "jpeg"
        elif ext in {"png", "webp", "gif"}:
            fmt = ext
        else:
            # Seedream 文档示例允许 <图片格式>，这里兜底按 png 处理
            fmt = "png"

        raw = path.read_bytes()
        b64 = base64.b64encode(raw).decode("utf-8")
        return f"data:image/{fmt};base64,{b64}"

    def _build_edit_prompt(self, user_prompt: str, has_mask: bool = False, has_reference: bool = False) -> str:
        """Build prompt for image editing
        基础提示词 + 用户输入提示词
        IMAGE 1 (scene with sketch)
        IMAGE 2 (mask - colored area)
        IMAGE OTHER (reference)
        """

        if user_prompt == "[智能修复]":  # 智能修复的提示词
            base_prompt = EDIT_SMART_REPAIR
            return base_prompt

        if has_mask and has_reference:  # 有遮罩和参考图片
            base_prompt = EDIT_WITH_MASK_AND_REFERENCES
            return base_prompt
        elif has_mask:  # 有遮罩
            base_prompt = EDIT_WITH_MASK
        elif has_reference:  # 有参考图片
            base_prompt = EDIT_WITH_REFERENCES
        else:
            # 没有遮罩也没有参考图片,只有提示词输入的基本提示词
            base_prompt = EDIT_BASE_PROMPT
        if user_prompt.strip():
            return f"{base_prompt}\n\n用户的编辑说明:\n{user_prompt.strip()}"
        else:
            return base_prompt

    def _build_generate_prompt(
            self,
            user_prompt: str,
            has_reference: bool = False,
            is_color_render: bool = False,
    ) -> str:
        if is_color_render:
            if has_reference:
                base_prompt = GENERATE_RENDER_WITH_REFERENCE
            else:
                base_prompt = GENERATE_RENDER_WITHOUT_REFERENCE
        else:
            if has_reference:
                base_prompt = GENERATE_DEPTH_MAP_WITHOUT_REFERENCE
            else:
                base_prompt = GENERATE_DEPTH_MAP_WITH_REFERENCE
        if user_prompt.strip():
            return f"{base_prompt}\n\nUSER PROMPT (EXECUTE THIS): {user_prompt.strip()}"
        return base_prompt
