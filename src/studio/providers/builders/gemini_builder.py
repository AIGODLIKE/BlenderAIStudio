import bpy
import base64
from bpy.app.translations import pgettext as _T
from typing import Dict, Any, TYPE_CHECKING
from copy import deepcopy
from pathlib import Path
from .base import RequestBuilder, RequestData
from .prompt import (
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
from .... import logger

from ....utils import calc_appropriate_aspect_ratio

if TYPE_CHECKING:
    from ...config.model_registry import ModelConfig


class GeminiImageGenerateBuilder(RequestBuilder):
    """Gemini 图像请求构建器

    支持多种功能：
    - generate: 图像生成（从深度图/渲染图）
    - edit: 图像编辑（基于提示词和遮罩）
    - transfer: 风格迁移（基于参考图）

    根据 params 中的 'action' 字段选择不同的构建逻辑。
    """

    def __init__(self, is_pro: bool = False):
        self.is_pro = is_pro

    def build(self, params: Dict[str, Any], model_config: "ModelConfig", auth_mode: str, credentials: Dict[str, str]) -> RequestData:
        """构建 Gemini 图像请求

        Args:
            params: 参数字典（已由 InputProcessor 处理），支持以下字段：
                - image_path: 输入图片路径（已由 InputProcessor 准备好）
                - prompt/user_prompt: 用户提示词
                - reference_images: 参考图片路径列表
                - mask_path: 遮罩图片路径（edit 模式）
                - is_color_render: 是否为彩色渲染
                - width, height: 输出尺寸
                - image_size: 分辨率
                - aspect_ratio: 宽高比
                - __action: 功能类型（"generate", "edit", "transfer"），默认为 model_config.default_action
            model_config: 模型配置对象
            auth_mode: 认证模式
            credentials: 认证凭证

        Returns:
            RequestData 对象

        Raises:
            ValueError: 不支持的 action 类型
        """
        # 1. 预处理参数（标准化字段名）
        params = self._preprocess_params(params)

        # 获取功能类型
        action = params.get("__action", model_config.default_action)

        # 验证功能支持
        if not model_config.supports_action(action):
            error_msg: str = _T("Action '{action}' not supported for model '{model_name}'.")
            error_msg = error_msg.format(action=action, model_name=model_config.model_name)
            raise ValueError(error_msg)

        # 2. 构建 URL
        url = model_config.build_api_url(auth_mode)

        # 3. 构建 Headers
        endpoint = model_config.get_endpoint(auth_mode)
        headers = self._build_headers(
            endpoint["headers"],
            credentials,
            model_config,
            params,
        )

        # 4. 构建 Payload（根据 action 选择不同的构建逻辑）
        if action == "generate":
            payload = self._build_generate_payload(params)
        elif action == "edit":
            payload = self._build_edit_payload(params)
        elif action == "transfer":
            payload = self._build_transfer_payload(params)
        else:
            raise ValueError(_T("Unknown action: '{action}'.").format(action=action))

        # 5. 返回完整请求数据
        return RequestData(
            url=url,
            headers=headers,
            payload=payload,
            method=endpoint.get("method", "POST"),
            timeout=300,
        )

    def _preprocess_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """预处理参数

        处理从 Client 传来的原始参数，转换为 Builder 需要的格式。
        包括：
        - 处理提示词 (prompt → user_prompt)
        - 处理内部提示词 (use_internal_prompt)
        - 处理分辨率 (resolution → width/height)
        - 处理宽高比

        Args:
            params: 原始参数

        Returns:
            处理后的参数
        """
        processed = deepcopy(params)

        # 1. 处理提示词：优先使用 user_prompt，如果没有则使用 prompt
        if "user_prompt" not in processed and "prompt" in processed:
            processed["user_prompt"] = processed["prompt"]

        # 2. 处理提示词（如果启用了 use_internal_prompt）
        if processed.get("__use_internal_prompt", False):
            itype = processed.get("input_image_type", "NoInput")
            user_prompt = ""
            if itype == "NoInput":
                user_prompt = "所有图片均为参考图, "
            elif itype == "CameraRender":
                user_prompt = "第一张图是渲染图(原图)，其他为参考图, "
            elif itype == "CameraDepth":
                user_prompt = "第一张图是深度图，其他为参考图, "
            user_prompt += processed.get("user_prompt", "")
            processed["user_prompt"] = user_prompt

        # 3. 处理分辨率：将字符串转换为 width/height
        if "resolution" in processed and ("width" not in processed or "height" not in processed):
            resolution_str = processed["resolution"]
            resolution_map = {
                "1K": (1024, 1024),
                "2K": (2048, 2048),
                "4K": (4096, 4096),
            }
            width, height = resolution_map.get(resolution_str, (1024, 1024))
            processed["width"] = width
            processed["height"] = height

        # 4. 处理宽高比
        if "aspect_ratio" in processed:
            aspect_ratio = processed["aspect_ratio"]

            if aspect_ratio == "Auto":
                try:
                    scene_width = bpy.context.scene.render.resolution_x
                    scene_height = bpy.context.scene.render.resolution_y
                    aspect_ratio = calc_appropriate_aspect_ratio(scene_width, scene_height)
                except Exception:
                    aspect_ratio = "1:1"  # 默认值

            processed["aspect_ratio"] = aspect_ratio

        # 5. 设置默认 action
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
        """构建 Headers

        支持占位符替换：
        - {api_key}: API Key
        - {token}: 账号 Token
        - {modelId}: 模型 ID
        - {size}: 图片尺寸（从 params 中获取）
        """
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
        """构建图像生成 payload（原 _build_payload 逻辑）"""
        image_path = params.get("main_image", "")
        user_prompt = params.get("user_prompt", "")
        ref_images_path = params.get("reference_images", [])
        is_color_render = params.get("is_color_render", False)
        width = params.get("width", 1024)
        height = params.get("height", 1024)
        aspect_ratio = params.get("aspect_ratio", "1:1")

        # 20MB
        total_image_size_limit = 20 * 1024 * 1024
        total_image_size = 0
        all_image_paths = ref_images_path + ([image_path] if image_path else [])
        for image_path in all_image_paths:
            total_image_size += Path(image_path).stat().st_size
        if total_image_size > total_image_size_limit:
            raise ValueError("Total image size exceeds the limit of 20MB.")

        # 构建完整提示词
        full_prompt = self._build_generate_prompt(
            user_prompt,
            has_reference=bool(ref_images_path),
            is_color_render=is_color_render,
        )

        # 控制输出分辨率
        full_prompt += f"\n\nCRITICAL OUTPUT SETTING: Generate image EXACTLY at {width}x{height} pixels."

        parts = [{"text": full_prompt}]
        # Build parts array
        if image_path:
            with open(image_path, "rb") as f:
                image_base64 = base64.b64encode(f.read()).decode("utf-8")
            part = {"inline_data": {"mime_type": "image/png", "data": image_base64}}
            parts.append(part)

        # Add reference image (Style) - SECOND image
        for reference_image_path in ref_images_path:
            with open(reference_image_path, "rb") as f:
                reference_base64 = base64.b64encode(f.read()).decode("utf-8")
            part = {"inline_data": {"mime_type": "image/png", "data": reference_base64}}
            parts.append(part)

        # Map resolution to string format expected by API
        image_size = "1K"
        if width >= 4096 or height >= 4096:
            image_size = "4K"
        elif width >= 2048 or height >= 2048:
            image_size = "2K"

        image_config = {}
        if self.is_pro:
            image_config["imageSize"] = image_size
        image_config["aspectRatio"] = aspect_ratio
        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {
                "temperature": 0.8,
                "maxOutputTokens": 32768,
                "candidateCount": 1,
                "responseModalities": ["IMAGE"],
                "imageConfig": image_config,
            },
        }
        return payload

    def _build_edit_payload(self, params: Dict[str, Any]) -> dict:
        """构建图像编辑 payload"""
        image_path = params.get("main_image", "")
        user_prompt = params.get("user_prompt", "")
        ref_images_path = params.get("reference_images", [""])
        mask_image_path = ref_images_path[0] if ref_images_path else ""
        image_size = params.get("resolution", "1K")
        aspect_ratio = params.get("aspect_ratio", "1:1")

        # 20MB
        total_image_size_limit = 20 * 1024 * 1024
        total_image_size = 0
        all_image_paths = ref_images_path + ([image_path] if image_path else [])
        for image_path in all_image_paths:
            total_image_size += Path(image_path).stat().st_size
        if total_image_size > total_image_size_limit:
            raise ValueError("Total image size exceeds the limit of 20MB.")

        prompt = self._build_edit_prompt(
            user_prompt,
            has_mask=bool(mask_image_path),
            has_reference=bool(ref_images_path[1:]),
        )
        parts = [{"text": prompt}]

        def add_part(image_file_path):
            with open(image_file_path, "rb") as f:
                image_base64 = base64.b64encode(f.read()).decode("utf-8")
            part = {"inline_data": {"mime_type": "image/png", "data": image_base64}}
            parts.append(part)
            logger.info(f"add_part {image_file_path}")

        add_part(image_path)  # 添加主图
        # 遮罩默认在第一张参考图片位置
        for ref_path in ref_images_path:
            # mask为空时过滤掉
            if not ref_path:
                continue
            add_part(ref_path)

        image_config = {}
        if self.is_pro:
            image_config["imageSize"] = image_size
        image_config["aspectRatio"] = aspect_ratio

        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {
                "temperature": 0.7,  # Lower temperature for more faithful edits
                "maxOutputTokens": 32768,
                "candidateCount": 1,
                "responseModalities": ["TEXT", "IMAGE"],
                "imageConfig": image_config,
            },
        }
        return payload

    def _build_transfer_payload(self, params: Dict[str, Any]) -> dict:
        """构建风格迁移 payload

        注：风格迁移可能与图像生成使用相同的 payload 格式，
        只是参考图片的用途不同。这里先复用 generate 逻辑。
        """
        return self._build_generate_payload(params)

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
            return f"{base_prompt}\n\nUSER'S EDIT INSTRUCTIONS:\n{user_prompt.strip()}"
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
