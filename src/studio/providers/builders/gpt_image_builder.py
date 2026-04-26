import os
from copy import deepcopy
from pathlib import Path
from typing import Dict, Any, TYPE_CHECKING, List, Optional, Tuple

from bpy.app.translations import pgettext as _T

from .base import RequestBuilder, RequestData
from .seedream_prompt import (
    GENERATE_RENDER_WITH_REFERENCE,
    GENERATE_RENDER_WITHOUT_REFERENCE,
    GENERATE_DEPTH_MAP_WITH_REFERENCE,
    GENERATE_DEPTH_MAP_WITHOUT_REFERENCE,
    EDIT_SMART_REPAIR,
    EDIT_WITH_MASK_AND_REFERENCES,
    EDIT_WITH_MASK,
    EDIT_WITH_REFERENCES,
    EDIT_BASE_PROMPT,
)
from ....utils import get_pref
from ....utils.image_processor import ImageProcessor

if TYPE_CHECKING:
    from ...config.model_registry import ModelConfig


class GPTImageGenerateBuilder(RequestBuilder):
    """GPT Image (gpt-image-1) 请求构建器

    走 Account 模式，请求通过后端代理转发。
    支持 generate / edit 两种 action。
    """

    def build(
        self,
        params: Dict[str, Any],
        model_config: "ModelConfig",
        auth_mode: str,
        credentials: Dict[str, str],
    ) -> RequestData:
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

        # endpoint 可配置 payload_model，用于 payload 中的 model 字段
        # 与 header 中的 X-Model-ID（雪花ID）分离
        payload_model = endpoint.get("payload_model") or model_config.model_id

        if action == "generate":
            payload = self._build_generate_payload(params, model_config, payload_model, action="generate")
        elif action == "edit":
            payload = self._build_edit_payload(params, model_config, payload_model)
        else:
            raise ValueError(_T("Unknown action: '{action}'.").format(action=action))

        return RequestData(
            url=url,
            headers=headers,
            payload=payload,
            method=endpoint.get("method", "POST"),
            timeout=120,
        )

    def _preprocess_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        processed = deepcopy(params)
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
                for cred_key, cred_value in credentials.items():
                    value = value.replace(f"{{{cred_key}}}", cred_value)
                if "{size}" in value:
                    value = value.replace("{size}", self._resolve_size(params))
            headers[key] = value
        return headers

    def _build_generate_payload(
        self,
        params: Dict[str, Any],
        model_config: "ModelConfig",
        payload_model: str,
        action: str = "generate",
    ) -> dict:
        """构建 payload；含参考图时 images 对齐 OpenAI 结构。

        OpenAI images（generations / edits）中输入图为对象数组，每项为
        ``{"image_url": "<url 或 data URL>"}`` 或 ``{"file_id": "..."}``，
        见 https://developers.openai.com/api/reference/resources/images/methods/edit

        edits 的 mask 单独为 ``{"image_url": "..."}``，不能与待编辑主图混在同一列表。
        """
        ref_images_path = params.get("reference_images", [])
        prompt = self._build_generate_prompt(
            params,
            has_reference=bool(ref_images_path),
        )

        size = self._resolve_size(params)
        images, mask_obj = self._collect_openai_input_images(params, action)

        payload: Dict[str, Any] = {
            "model": payload_model,
            "prompt": prompt,
            "n": 1,
            "size": size,
            "quality": params.get("quality", "auto"),
            "background": params.get("background", "auto"),
            "output_format": "png",
        }

        if images:
            payload["image"] = images
        if mask_obj is not None:
            payload["mask"] = mask_obj
        return payload

    def _build_edit_payload(self, params: Dict[str, Any], model_config: "ModelConfig", payload_model: str) -> dict:
        prompt = params.get("prompt", "").strip()
        ref_images_path = params.get("reference_images", [""])
        mask_image_path = ref_images_path[0] if ref_images_path else ""
        prompt = self._build_edit_prompt(
            prompt,
            has_mask=bool(mask_image_path),
            has_reference=bool(ref_images_path[1:]),
        )
        payload = self._build_generate_payload(params, model_config, payload_model, action="edit")
        payload["prompt"] = prompt
        return payload

    def _resolve_size(self, params: Dict[str, Any]) -> str:
        # 优先使用 resolution（与其他模型保持一致）
        resolution = params.get("resolution")
        if isinstance(resolution, str) and resolution.strip():
            return resolution.strip()

        size = params.get("size")
        if isinstance(size, str) and size.strip():
            return size.strip()

        w = params.get("width")
        h = params.get("height")
        if isinstance(w, int) and isinstance(h, int) and w > 0 and h > 0:
            return f"{w}x{h}"

        return "auto"

    def _as_list_param(self, v: Any) -> List[Any]:
        if v is None:
            return []
        if isinstance(v, list):
            return v
        return [v]

    def _existing_file_paths(self, items: List[Any]) -> List[str]:
        paths: List[str] = []
        for item in items:
            if not item:
                continue
            if isinstance(item, (str, Path)):
                p = Path(item)
                if p.exists() and p.is_file():
                    paths.append(str(p))
        return paths

    def _paths_to_openai_image_objects(self, paths: List[str]) -> List[Dict[str, str]]:
        """OpenAI ``images`` / ``mask``：``{ "image_url": data_url 或 https URL }``。"""
        if not paths:
            return []
        prep = ImageProcessor.prepare_images_for_upload(paths)
        try:
            return [
                ImageProcessor.image_to_base64(pt, output_format="data_url")
                for pt in prep.paths
            ]
        finally:
            for t in prep.temp_files:
                try:
                    os.remove(t)
                except OSError:
                    pass

    def _single_openai_image_object(self, path: str) -> Optional[Dict[str, str]]:
        objs = self._paths_to_openai_image_objects([path])
        return objs[0] if objs else None

    def _collect_openai_input_images(
        self, params: Dict[str, Any], action: str
    ) -> Tuple[List[Dict[str, str]], Optional[Dict[str, str]]]:
        """返回 (images 数组, 可选 mask 对象)，格式符合 OpenAI Images API。"""
        if action == "edit":
            ref_list = self._as_list_param(params.get("reference_images"))
            mask_candidates: List[Any] = []
            if params.get("mask_path"):
                mask_candidates.append(params.get("mask_path"))
            if ref_list:
                mask_candidates.append(ref_list[0])
            mask_paths = self._existing_file_paths(mask_candidates)
            mask_path = mask_paths[0] if mask_paths else ""
            mask_obj = self._single_openai_image_object(mask_path) if mask_path else None

            image_path_items: List[Any] = []
            image_path_items += self._as_list_param(params.get("image"))
            image_path_items += self._as_list_param(params.get("main_image"))
            image_path_items += self._as_list_param(params.get("image_path"))
            if len(ref_list) > 1:
                image_path_items += ref_list[1:]

            paths = self._existing_file_paths(image_path_items)
            # 去重且保持顺序（避免 mask 与主图路径重复时写两次）
            seen: set[str] = set()
            uniq_paths: List[str] = []
            for p in paths:
                if p not in seen:
                    seen.add(p)
                    uniq_paths.append(p)

            return self._paths_to_openai_image_objects(uniq_paths), mask_obj

        # generate：参考图与可选 mask_path 一并作为输入图列表
        candidates: List[Any] = []
        candidates += self._as_list_param(params.get("image"))
        candidates += self._as_list_param(params.get("main_image"))
        candidates += self._as_list_param(params.get("image_path"))
        candidates += self._as_list_param(params.get("mask_path"))
        candidates += self._as_list_param(params.get("reference_images"))
        paths = self._existing_file_paths(candidates)
        return self._paths_to_openai_image_objects(paths), None

    def _build_edit_prompt(self, user_prompt: str, has_mask: bool = False, has_reference: bool = False) -> str:
        if get_pref().disable_system_prompt:
            return user_prompt

        if user_prompt == "[智能修复]":
            return EDIT_SMART_REPAIR

        if has_mask and has_reference:
            base_prompt = EDIT_WITH_MASK_AND_REFERENCES
            return base_prompt
        elif has_mask:
            base_prompt = EDIT_WITH_MASK
        elif has_reference:
            base_prompt = EDIT_WITH_REFERENCES
        else:
            base_prompt = EDIT_BASE_PROMPT

        if user_prompt.strip():
            return f"{base_prompt}\n\n用户的编辑说明:\n{user_prompt.strip()}"
        return base_prompt

    def _build_generate_prompt(self, params: dict, has_reference: bool = False) -> str:
        user_prompt = params.get("prompt", "").strip()
        if self._should_exclude_system_prompt(params):
            return user_prompt

        is_color_render = params.get("input_image_type", "") != "CameraDepth"

        if is_color_render:
            if has_reference:
                base_prompt = GENERATE_RENDER_WITH_REFERENCE
            else:
                base_prompt = GENERATE_RENDER_WITHOUT_REFERENCE
        else:
            if has_reference:
                base_prompt = GENERATE_DEPTH_MAP_WITH_REFERENCE
            else:
                base_prompt = GENERATE_DEPTH_MAP_WITHOUT_REFERENCE

        if user_prompt.strip():
            return f"{base_prompt}\n\n用户的编辑说明: {user_prompt.strip()}"
        return base_prompt

    def _should_exclude_system_prompt(self, params: Dict[str, Any]) -> bool:
        return params.get("__disable_system_prompt", False) or get_pref().disable_system_prompt
