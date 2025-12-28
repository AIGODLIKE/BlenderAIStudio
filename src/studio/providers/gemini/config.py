import base64

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


class Payload:
    def build_payload(self) -> dict:
        raise NotImplementedError


class GeminiImageGeneratePayload(Payload):
    def __init__(
        self,
        image_path: str,
        user_prompt: str,
        reference_images_path: list[str],
        is_color_render: bool = False,
        width: int = 1024,
        height: int = 1024,
        aspect_ratio: str = "1:1",
    ):
        self.image_path: str = image_path
        self.user_prompt: str = user_prompt
        self.reference_images_path: list[str] = reference_images_path
        self.is_color_render: bool = is_color_render
        self.width: int = width
        self.height: int = height
        self.aspect_ratio: str = aspect_ratio

    def build_payload(self) -> dict:
        # 构建完整提示词
        full_prompt = self._build_generate_prompt(
            self.user_prompt,
            has_reference=bool(self.reference_images_path),
            is_color_render=self.is_color_render,
        )

        # 控制输出分辨率
        full_prompt += f"\n\nCRITICAL OUTPUT SETTING: Generate image EXACTLY at {self.width}x{self.height} pixels."

        parts = [{"text": full_prompt}]
        # Build parts array
        if self.image_path:
            with open(self.image_path, "rb") as f:
                image_base64 = base64.b64encode(f.read()).decode("utf-8")
            part = {"inline_data": {"mime_type": "image/png", "data": image_base64}}
            parts.append(part)

        # Add reference image (Style) - SECOND image
        for reference_image_path in self.reference_images_path:
            with open(reference_image_path, "rb") as f:
                reference_base64 = base64.b64encode(f.read()).decode("utf-8")
            part = {"inline_data": {"mime_type": "image/png", "data": reference_base64}}
            parts.append(part)

        # Map resolution to string format expected by API
        resolution_str = "1K"
        if self.width >= 4096 or self.height >= 4096:
            resolution_str = "4K"
        elif self.width >= 2048 or self.height >= 2048:
            resolution_str = "2K"

        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {
                "temperature": 0.8,
                "maxOutputTokens": 32768,
                "candidateCount": 1,
                "responseModalities": ["IMAGE"],
                "imageConfig": {
                    "imageSize": resolution_str,
                    "aspectRatio": self.aspect_ratio,
                },
            },
        }
        return payload

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


class GeminiImageEditPayload(Payload):
    def __init__(
        self,
        image_path: str,
        edit_prompt: str,
        mask_path: str = None,
        reference_image_path: list[str] = None,
        resolution: str = "1K",
        aspect_ratio: str = "1:1",
    ):
        """
        基于提示词(和遮罩, 可选)编辑现有图像
        图片顺序很重要
        IMAGE 1 (scene with sketch)
        IMAGE 2 (mask - colored area)
        IMAGE OTHER (reference)

        Args:
            image_path: 编辑输入图像
            edit_prompt: 编辑提示词
            mask_path: 遮罩图像(可选) white = edit, black = keep
            reference_image_path: 风格参考图(可选)
            width, height: 目标分辨率(可选) 0为自动匹配输入

        Returns: (image_data, mime_type)
        :param aspect_ratio:
        :param image_path:
        :param edit_prompt:
        :param mask_path:
        :param reference_image_path:
        :param resolution:
        """
        self.image_path: str = image_path
        self.edit_prompt: str = edit_prompt
        self.mask_path: str = mask_path
        self.reference_image_path: list[str] = reference_image_path
        self.resolution: str = resolution
        self.aspect_ratio: str = aspect_ratio

    def build_payload(self) -> dict:
        prompt = self._build_edit_prompt(
            self.edit_prompt,
            has_mask=bool(self.mask_path),
            has_reference=bool(self.reference_image_path),
        )
        parts = [{"text": prompt}]

        def add_part(image_file_path):
            with open(image_file_path, "rb") as f:
                image_base64 = base64.b64encode(f.read()).decode("utf-8")
            part = {"inline_data": {"mime_type": "image/png", "data": image_base64}}
            parts.append(part)
            print("add_part", image_file_path)

        add_part(self.image_path)  # 添加主图
        # 添加遮罩
        if self.mask_path:
            add_part(self.mask_path)
        for ref_path in self.reference_image_path:
            add_part(ref_path)

        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {
                "temperature": 0.7,  # Lower temperature for more faithful edits
                "maxOutputTokens": 32768,
                "candidateCount": 1,
                "responseModalities": ["TEXT", "IMAGE"],
                "imageConfig": {
                    "imageSize": self.resolution,
                    "aspectRatio": self.aspect_ratio,
                },
            },
        }
        return payload

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
            base_prompt = EDIT_WITH_MASK_AND_REFERENCES % user_prompt
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
