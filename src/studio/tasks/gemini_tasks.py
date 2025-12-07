import base64
import json
import tempfile
from pathlib import Path
from typing import Tuple, Optional

import OpenImageIO as oiio
import numpy as np
import requests

from .task import Task, TaskResult


class GeminiTaskBase(Task):
    """
    Gemini 任务基类

    提供 Gemini API 相关的通用功能：
    - API 客户端管理
    - 重试机制
    - 图片验证
    """

    def __init__(self, task_name: str, api_key: str, max_retries: int = 3):
        """
        初始化 Gemini 任务

        Args:
            task_name: 任务名称
            api_key: Gemini API Key
            max_retries: 最大重试次数
        """
        super().__init__(task_name)
        self.api_key = api_key
        self.max_retries = max_retries
        self.retry_count = 0
        self.api_client: GeminiAPI = None

    def prepare(self) -> bool:
        """准备 API 客户端"""
        try:
            # 验证 API Key
            if not self.api_key or not self.api_key.strip():
                self.update_progress(0, "API Key 未设置")
                return False
            # 创建 API 客户端
            self.api_client = GeminiAPI(self.api_key)
            self.update_progress(0, "API 客户端已准备")
            return True
        except Exception as e:
            self.update_progress(0, f"准备失败: {str(e)}")
            return False

    def cleanup(self) -> None:
        """清理资源"""
        self.api_client = None

    def _validate_image_path(self, image_path: str, param_name: str = "图片") -> bool:
        """
        验证图片路径

        Args:
            image_path: 图片路径
            param_name: 参数名称（用于错误提示）

        Returns:
            是否有效
        """
        if not image_path:
            self.update_progress(message=f"{param_name}路径为空")
            return False

        path = Path(image_path)
        if not path.exists():
            self.update_progress(message=f"{param_name}不存在: {image_path}")
            return False

        if not path.is_file():
            self.update_progress(message=f"{param_name}不是文件: {image_path}")
            return False

        # 检查文件大小（可选）
        file_size = path.stat().st_size
        max_size = 20 * 1024 * 1024  # 20MB
        if file_size > max_size:
            self.update_progress(message=f"{param_name}过大: {file_size / 1024 / 1024:.1f}MB")
            return False
        return True


class GeminiImageGenerationTask(GeminiTaskBase):
    """
    Gemini 图片生成任务

    基于深度图/彩色渲染图 + 提示词生成新图片
    """

    def __init__(
        self,
        api_key: str,
        image_path: str,
        user_prompt: str,
        reference_images_path: list[str],
        is_color_render: bool = False,
        width: int = 1024,
        height: int = 1024,
        aspect_ratio: str = "1:1",
        max_retries: int = 3,
    ):
        """
        初始化图片生成任务

        Args:
            api_key: Gemini API Key
            image_path: 深度图/输入图片路径
            user_prompt: 用户提示词
            reference_images_path: 参考图片路径（可选）
            is_color_render: 是否为彩色渲染（True=彩色, False=深度图）
            width: 输出宽度
            height: 输出高度
            max_retries: 最大重试次数
        """
        super().__init__("Gemini 图片生成", api_key, max_retries)

        self.image_path = image_path
        self.user_prompt = user_prompt
        self.reference_images_path = reference_images_path
        self.is_color_render = is_color_render
        self.width = width
        self.height = height
        self.aspect_ratio = aspect_ratio

        # 设置总步骤数
        self.progress.total_steps = 4

    def prepare(self) -> bool:
        """准备任务"""
        if not super().prepare():
            return False

        # 验证输入图片
        if not self._validate_image_path(self.image_path, "输入图片"):
            return False

        # 验证参考图片（如果提供）
        for ref_image_path in self.reference_images_path:
            if not self._validate_image_path(ref_image_path, "参考图片"):
                return False

        self.update_progress(1, "参数验证完成")
        return True

    def execute(self) -> TaskResult:
        """执行图片生成"""
        try:
            import time

            time.sleep(1)
            self.update_progress(2, "正在调用 Gemini API...")

            # 调用 API
            image_data, mime_type = b"", "image/png"
            image_data, mime_type = self.api_client.generate_image(
                depth_image_path=self.image_path,
                user_prompt=self.user_prompt,
                reference_images_path=self.reference_images_path,
                is_color_render=self.is_color_render,
                width=self.width,
                height=self.height,
                aspect_ratio=self.aspect_ratio,
            )
            time.sleep(1)

            self.update_progress(3, "API 调用成功，处理响应...")

            # 构建结果
            result_data = {
                "image_data": image_data,
                "mime_type": mime_type,
                "width": self.width,
                "height": self.height,
            }
            time.sleep(1)

            self.update_progress(4, "图片生成完成")
            time.sleep(1)

            return TaskResult.success_result(
                data=result_data,
                metadata={
                    "prompt": self.user_prompt,
                    "is_color_render": self.is_color_render,
                    "has_reference": bool(self.reference_images_path),
                },
            )

        except Exception as e:
            error_msg = f"图片生成失败: {str(e)}"
            self.update_progress(message=error_msg)
            return TaskResult.failure_result(e, error_msg)


class GeminiImageEditTask(GeminiTaskBase):
    """
    Gemini 图片编辑任务

    基于现有图片 + 提示词 + 遮罩进行编辑
    """

    def __init__(
        self,
        api_key: str,
        image_path: str,
        edit_prompt: str,
        mask_path: Optional[str] = None,
        reference_images_path: Optional[str] | list[str] = None,
        width: int = 0,
        height: int = 0,
        aspect_ratio: str = "1:1",
        max_retries: int = 3,
    ):
        """
        初始化图片编辑任务

        Args:
            api_key: Gemini API Key
            image_path: 待编辑图片路径
            edit_prompt: 编辑提示词
            mask_path: 遮罩图片路径（可选）
            reference_images_path: 参考图片路径（可选）
            width: 输出宽度（0=自动）
            height: 输出高度（0=自动）
            max_retries: 最大重试次数
        """
        super().__init__("Gemini 图片编辑", api_key, max_retries)

        self.image_path = image_path
        self.edit_prompt = edit_prompt
        self.mask_path = mask_path
        self.reference_images_path = reference_images_path
        self.width = width
        self.height = height
        self.aspect_ratio = aspect_ratio

        self.progress.total_steps = 4

    def prepare(self) -> bool:
        """准备任务"""
        if not super().prepare():
            return False

        # 验证输入图片
        if not self._validate_image_path(self.image_path, "待编辑图片"):
            return False

        # 验证遮罩（如果提供）
        if self.mask_path:
            if not self._validate_image_path(self.mask_path, "遮罩图片"):
                return False

        # 验证参考图片（如果提供）
        if self.reference_images_path:
            if isinstance(self.reference_images_path, list):
                for path in self.reference_images_path:
                    if not self._validate_image_path(path, "参考图片"):
                        return False
            else:
                if not self._validate_image_path(self.reference_images_path, "参考图片"):
                    return False

        self.update_progress(1, "参数验证完成")
        return True

    def execute(self) -> TaskResult:
        """执行图片编辑"""
        try:
            self.update_progress(2, "正在调用 Gemini API...")

            # 调用 API
            image_data, mime_type = self.api_client.edit_image(
                image_path=self.image_path,
                edit_prompt=self.edit_prompt,
                mask_path=self.mask_path,
                reference_image_path=self.reference_images_path,
                width=self.width,
                height=self.height,
            )

            self.update_progress(3, "API 调用成功，处理响应...")

            # 构建结果
            result_data = {
                "image_data": image_data,
                "mime_type": mime_type,
            }

            self.update_progress(4, "图片编辑完成")

            return TaskResult.success_result(
                data=result_data,
                metadata={
                    "prompt": self.edit_prompt,
                    "has_mask": bool(self.mask_path),
                    "has_reference": bool(self.reference_images_path),
                },
            )

        except Exception as e:
            error_msg = f"图片编辑失败: {str(e)}"
            self.update_progress(message=error_msg)
            return TaskResult.failure_result(e, error_msg)


class GeminiStyleTransferTask(GeminiTaskBase):
    """
    Gemini 风格迁移任务

    将参考图片的风格应用到目标图片上
    """

    def __init__(
        self,
        api_key: str,
        target_image_path: str,
        style_image_path: str,
        style_prompt: str = "",
        width: int = 0,
        height: int = 0,
        max_retries: int = 3,
    ):
        """
        初始化风格迁移任务

        Args:
            api_key: Gemini API Key
            target_image_path: 目标图片路径
            style_image_path: 风格参考图片路径
            style_prompt: 风格描述提示词（可选）
            width: 输出宽度（0=自动）
            height: 输出高度（0=自动）
            max_retries: 最大重试次数
        """
        super().__init__("Gemini 风格迁移", api_key, max_retries)

        self.target_image_path = target_image_path
        self.style_image_path = style_image_path
        self.style_prompt = style_prompt
        self.width = width
        self.height = height

        self.progress.total_steps = 4

    def prepare(self) -> bool:
        """准备任务"""
        if not super().prepare():
            return False

        # 验证目标图片
        if not self._validate_image_path(self.target_image_path, "目标图片"):
            return False

        # 验证风格图片
        if not self._validate_image_path(self.style_image_path, "风格图片"):
            return False

        self.update_progress(1, "参数验证完成")
        return True

    def execute(self) -> TaskResult:
        """执行风格迁移"""
        try:
            self.update_progress(2, "正在调用 Gemini API...")

            # 使用 edit_image 方法实现风格迁移
            image_data, mime_type = self.api_client.edit_image(
                image_path=self.target_image_path,
                edit_prompt=self.style_prompt or "应用参考图片的风格",
                reference_image_path=self.style_image_path,
                width=self.width,
                height=self.height,
            )

            self.update_progress(3, "API 调用成功，处理响应...")

            # 构建结果
            result_data = {
                "image_data": image_data,
                "mime_type": mime_type,
            }

            self.update_progress(4, "风格迁移完成")

            return TaskResult.success_result(
                data=result_data,
                metadata={
                    "style_prompt": self.style_prompt,
                },
            )

        except Exception as e:
            error_msg = f"风格迁移失败: {str(e)}"
            self.update_progress(message=error_msg)
            return TaskResult.failure_result(e, error_msg)


###############################################################################
#         Reference: https://github.com/kovname/nano-banana-render            #
###############################################################################


class GeminiAPIError(Exception):
    pass


class GeminiAPI:
    def __init__(self, api_key: str, model="models/gemini-3-pro-image-preview"):
        self.api_key = api_key
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"
        self.model = model

    def _build_generate_prompt(
        self,
        user_prompt: str,
        has_reference: bool = False,
        is_color_render: bool = False,
    ) -> str:
        if is_color_render:
            if has_reference:
                base_prompt = (
                    "You are receiving TWO images:\n\n"
                    "IMAGE 1 (3D Render - YOUR STRUCTURE SOURCE):\n"
                    "- This is the GEOMETRY and LAYOUT you must preserve\n"
                    "- Use this EXCLUSIVELY for object positions and composition\n"
                    "- IGNORE its bad materials and lighting\n"
                    "- This defines WHAT is in the scene\n\n"
                    "IMAGE 2 (Style Reference - YOUR VISUAL GUIDE):\n"
                    "- This is the STYLE source (materials, lighting, colors)\n"
                    "- DO NOT copy objects from here, only their 'look'\n"
                    "- Apply this style to the geometry of IMAGE 1\n"
                    "- This defines HOW the scene looks\n\n"
                    "USER PROMPT (THE SUPREME COMMAND):\n"
                    "- The User Prompt below OVERRIDES everything else for CONTENT decisions.\n"
                    "- If user says 'black background', MAKE IT BLACK, even if Reference Image has a detailed background.\n"
                    "- If user says 'add neon lights', ADD THEM, even if Reference Image is dark.\n"
                    "- Reference Image is for STYLE (how things look), User Prompt is for CONTENT (what things are).\n"
                    "- CONFLICT RESOLUTION: User Prompt > Reference Image Style > Input Render\n\n"
                    "YOUR TASK - AGGRESSIVE TRANSFORMATION:\n"
                    "1. Keep ONLY the composition/layout from IMAGE 1 (Depth/Structure)\n"
                    "2. COMPLETELY REPLACE materials, lighting, colors with IMAGE 2's style (UNLESS User Prompt says otherwise)\n"
                    "3. Make materials look like IMAGE 2 (if metallic there → metallic here)\n"
                    "4. Match IMAGE 2's lighting direction, intensity, and color temperature\n"
                    "5. Use IMAGE 2's color palette - forget IMAGE 1's colors\n"
                    "6. Replicate IMAGE 2's atmosphere, depth, and mood\n"
                    "7. Think: 'IMAGE 1 is the skeleton, IMAGE 2 is the skin'\n\n"
                    "CRITICAL - DON'T BE CONSERVATIVE:\n"
                    "- If IMAGE 1 is blue but IMAGE 2 is warm → make it WARM\n"
                    "- If IMAGE 1 is flat but IMAGE 2 has depth → add DEPTH\n"
                    "- If IMAGE 1 is simple but IMAGE 2 is detailed → add DETAILS\n"
                    "- TRANSFORM aggressively, don't just 'improve' IMAGE 1\n"
                    "- STRICTLY FOLLOW IMAGE 1's GEOMETRY/LAYOUT. Do not add objects from IMAGE 2.\n"
                )
            else:
                base_prompt = (
                    "You are receiving a LOW-QUALITY 3D RENDER that needs COMPLETE VISUAL OVERHAUL:\n\n"
                    "INPUT IMAGE (ROUGH DRAFT ONLY):\n"
                    "- Amateur 3D render with placeholder materials and basic lighting\n"
                    "- Use ONLY for general composition and object positions\n"
                    "- Colors are WRONG, materials are FAKE, lighting is FLAT\n"
                    "- This is NOT the target quality - you must COMPLETELY rebuild it\n\n"
                    "YOUR MISSION - TOTAL TRANSFORMATION:\n"
                    "1. REPLACE all materials with photorealistic equivalents:\n"
                    "   - Metal → realistic metal with proper reflections, anisotropy, scratches\n"
                    "   - Plastic → varied surface finish, subtle color variation, wear\n"
                    "   - Wood → visible grain, natural color variation, texture depth\n"
                    "   - Glass → proper refraction, reflections, subtle imperfections\n"
                    "   - Fabric → weave patterns, soft shadows, natural draping\n\n"
                    "2. REBUILD lighting from scratch:\n"
                    "   - Add professional 3-point lighting or natural light sources\n"
                    "   - Strong shadows with soft edges\n"
                    "   - Realistic reflections and bounce light\n"
                    "   - Ambient occlusion in corners and crevices\n"
                    "   - Color temperature variation (warm/cool balance)\n\n"
                    "3. REIMAGINE colors:\n"
                    "   - Input colors are just suggestions - make them BETTER\n"
                    "   - Add professional color grading\n"
                    "   - Harmonious palette with contrast\n"
                    "   - Natural color variation within surfaces\n\n"
                    "4. ADD depth and atmosphere:\n"
                    "   - Volumetric lighting effects (god rays, haze)\n"
                    "   - Atmospheric perspective (depth fog)\n"
                    "   - Particle effects if appropriate (dust, moisture)\n"
                    "   - Background depth and detail\n\n"
                    "5. ENHANCE with imperfections:\n"
                    "   - Surface scratches, dents, wear patterns\n"
                    "   - Fingerprints on smooth surfaces\n"
                    "   - Dust accumulation in corners\n"
                    "   - Natural aging and weathering\n\n"
                    "USER PROMPT (THE SUPREME COMMAND):\n"
                    "- The User Prompt below is your PRIMARY INSTRUCTION for the transformation.\n"
                    "- If user says 'make it cyberpunk', use cyberpunk materials/lighting.\n"
                    "- If user says 'add rain', add rain.\n"
                    "- The input render provides the COMPOSITION, the User Prompt provides the STYLE/CONTENT.\n\n"
                    "CRITICAL MINDSET:\n"
                    "- Think: 'This is a SKETCH, not the final image'\n"
                    "- Your goal: 'Student work' → 'Professional portfolio piece'\n"
                    "- Be BOLD with changes - the input is intentionally low quality\n"
                    "- Don't preserve bad materials or flat lighting\n"
                    "- Make every surface, light, and color DRAMATICALLY better\n"
                    "- Aim for: movie VFX quality or high-end product photography\n"
                )
        else:
            if has_reference:
                base_prompt = (
                    "You are receiving TWO images with different purposes:\n\n"
                    "IMAGE 1 (Style Reference):\n"
                    "- Use ONLY for: color palette, material textures, lighting mood, surface details\n"
                    "- DO NOT copy: composition, object placement, camera angle\n"
                    "- Extract: visual aesthetics, aspect ratio\n\n"
                    "IMAGE 2 (Depth Map):\n"
                    "- Black and white gradient representing depth\n"
                    "- White = closest objects, Black = farthest objects\n"
                    "- Use for: scene composition, object placement, 3D structure\n"
                    "- This depth map shows the spatial layout\n\n"
                    "YOUR TASK:\n"
                    "1. Understand 3D scene structure from depth map (IMAGE 2)\n"
                    "2. Apply visual style from reference (IMAGE 1) to that structure\n"
                    "3. Create photorealistic render combining: reference style + depth map geometry\n"
                    "4. Match aspect ratio of reference image\n\n"
                    "USER PROMPT (THE SUPREME COMMAND):\n"
                    "- The User Prompt below OVERRIDES everything else for CONTENT decisions.\n"
                    "- If user says 'make it red', MAKE IT RED, even if Reference is blue.\n"
                    "- Reference Image is for STYLE only. User Prompt is for CONTENT.\n"
                    "- CONFLICT RESOLUTION: User Prompt > Reference Image Style > Depth Map\n"
                )
            else:
                base_prompt = (
                    "You are receiving a DEPTH MAP image:\n\n"
                    "DEPTH MAP:\n"
                    "- Black and white gradient representing depth\n"
                    "- White = closest objects, Black = farthest objects\n"
                    "- Shows spatial relationships and 3D structure\n\n"
                    "YOUR TASK:\n"
                    "1. Interpret the depth map to understand scene geometry\n"
                    "2. Generate photorealistic 3D render based on this structure\n"
                    "3. Choose appropriate materials, colors, and lighting\n\n"
                    "USER PROMPT (THE SUPREME COMMAND):\n"
                    "- The User Prompt below is your PRIMARY INSTRUCTION.\n"
                    "- You MUST follow the user's description for materials, colors, and lighting.\n"
                    "- The Depth Map provides the SHAPE, the User Prompt provides the LOOK.\n"
                )
        if user_prompt.strip():
            return f"{base_prompt}\n\nUSER PROMPT (EXECUTE THIS): {user_prompt.strip()}"
        return base_prompt

    def generate_image(
        self,
        depth_image_path: str,
        user_prompt: str,
        reference_images_path: list[str],
        is_color_render: bool = False,
        width: int = 1024,
        height: int = 1024,
        aspect_ratio: str = "1:1",
    ) -> Tuple[bytes, str]:
        """
        由深度图和提示词生成图像(可选使用参考图作为 风格化/材质)
        Args:
            is_color_render: 为True即使用常规eevee渲染, False代表使用深度图(mist)
            width, height: 输出分辨率
        Returns: (image_data, format)
        """
        try:
            # 构建完整提示词
            full_prompt = self._build_generate_prompt(
                user_prompt,
                has_reference=bool(reference_images_path),
                is_color_render=is_color_render,
            )

            # 控制输出分辨率
            full_prompt += f"\n\nCRITICAL OUTPUT SETTING: Generate image EXACTLY at {width}x{height} pixels."

            url = f"{self.base_url}/{self.model}:generateContent"
            headers = {
                "x-goog-api-key": self.api_key,
                "Content-Type": "application/json",
                "X-Goog-Api-Client": "python-blender-addon",
            }

            # Build parts array
            with open(depth_image_path, "rb") as f:
                image_base64 = base64.b64encode(f.read()).decode("utf-8")
            parts = [{"text": full_prompt}]
            part = {"inline_data": {"mime_type": "image/png", "data": image_base64}}
            parts.append(part)

            # Add reference image (Style) - SECOND image
            for reference_image_path in reference_images_path:
                with open(reference_image_path, "rb") as f:
                    reference_base64 = base64.b64encode(f.read()).decode("utf-8")
                part = {"inline_data": {"mime_type": "image/png", "data": reference_base64}}
                parts.append(part)

            # Map resolution to string format expected by API
            resolution_str = "1K"
            if width >= 4096 or height >= 4096:
                resolution_str = "4K"
            elif width >= 2048 or height >= 2048:
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
                        "aspectRatio": aspect_ratio,
                    },
                },
            }

            response = requests.post(url, headers=headers, json=payload, timeout=300)
            self._check_response_status(response)
            return self._parse_image_data_from_response_json(response.json())
        except requests.RequestException as e:
            raise GeminiAPIError(f"Network error: {str(e)}")
        except json.JSONDecodeError:
            raise GeminiAPIError("Failed to parse API response")
        except Exception as e:
            if isinstance(e, GeminiAPIError):
                raise
            raise GeminiAPIError(f"Unexpected error: {str(e)}")

    def _check_response_status(self, resp: requests.Response):
        code = resp.status_code
        if code == 403:
            raise GeminiAPIError("API key invalid or quota exceeded. Check your Google AI Studio account.")
        elif code == 429:
            retry_after = resp.headers.get("Retry-After", "unknown")
            raise GeminiAPIError(f"Rate limit exceeded. Retry after: {retry_after} seconds.")
        elif code == 400:
            raise GeminiAPIError(f"Bad request (400): {resp.text}")
        elif code != 200:
            raise GeminiAPIError(f"API request failed with status {code}: {resp.text}")

    def _parse_image_data_from_response_json(self, response_json: dict) -> Tuple[bytes, str]:
        if "candidates" not in response_json or not response_json["candidates"]:
            raise GeminiAPIError("No image generated. The model may have rejected the request.")

        candidate = response_json["candidates"][0]

        if "content" not in candidate:
            raise GeminiAPIError("Invalid response format - no content in candidate")

        parts: list[dict] = candidate["content"]["parts"]

        # 查找图片数据
        for part in parts:
            inline_data_key = None
            if "inline_data" in part:
                inline_data_key = "inline_data"
            elif "inlineData" in part:
                inline_data_key = "inlineData"

            if not inline_data_key:
                continue
            inline_data: dict = part[inline_data_key]

            data_key = None
            if "data" in inline_data:
                data_key = "data"
            elif "bytes" in inline_data:
                data_key = "bytes"

            if not data_key:
                continue

            if not inline_data[data_key]:
                continue
            mime_type = inline_data.get("mime_type", inline_data.get("mimeType", "image/jpeg"))
            image_data = base64.b64decode(inline_data[data_key])
            return image_data, mime_type

        # 无图时，返回占位符图片
        text_parts = [part.get("text", "") for part in parts]
        if any(text_parts):
            return self._create_placeholder_image()
        raise GeminiAPIError("No image data found in API response")

    def _create_placeholder_image(self) -> Tuple[bytes, str]:
        try:
            width, height = 100, 100
            png_data = self._create_empty_image(width, height, (0, 100, 200))
            return png_data, "image/png"
        except Exception as e:
            raise GeminiAPIError(f"Failed to create placeholder: {str(e)}")

    @staticmethod
    def _create_empty_image(width: int, height: int, color: tuple) -> bytes:
        with tempfile.NamedTemporaryFile(suffix=".png") as f:
            spec = oiio.ImageSpec(width, height, len(color), oiio.UINT8)
            out = oiio.ImageOutput.create(f.name)
            if not out:
                raise Exception(f"Could not create ImageOutput for {f.name}")
            pixels = np.full((height, width, len(color)), color, dtype=np.uint8)
            out.open(f.name, spec)
            out.write_image(pixels)
            out.close()
            png_data = Path(f.name).read_bytes()
            return png_data

    def edit_image(
        self,
        image_path: str,
        edit_prompt: str,
        mask_path: str = None,
        reference_image_path: str = None,
        width: int = 0,
        height: int = 0,
    ) -> Tuple[bytes, str]:
        """
        基于提示词(和遮罩, 可选)编辑现有图像

        Args:
            image_path: 编辑输入图像
            edit_prompt: 编辑提示词
            mask_path: 遮罩图像(可选) white = edit, black = keep
            reference_image_path: 风格参考图(可选)
            width, height: 目标分辨率(可选) 0为自动匹配输入

        Returns: (image_data, mime_type)
        """
        try:
            # Build edit prompt
            full_prompt = self._build_edit_prompt(
                edit_prompt,
                has_mask=bool(mask_path),
                has_reference=bool(reference_image_path),
            )
            return self._edit_with_rest(image_path, full_prompt, mask_path, reference_image_path, width, height)

        except Exception as e:
            if isinstance(e, GeminiAPIError):
                raise
            raise GeminiAPIError(f"Image edit failed: {str(e)}")

    def _build_edit_prompt(self, user_prompt: str, has_mask: bool = False, has_reference: bool = False) -> str:
        """Build prompt for image editing
        基础提示词 + 用户输入提示词
        IMAGE 1 (scene with sketch)
        IMAGE 2 (mask - colored area)
        IMAGE OTHER (reference)
        """

        # Special finalization mode
        if user_prompt == "[FINALIZE_COMPOSITE]":  # 最终合成的提示词
            base_prompt = (
                "COMPOSITE FINALIZATION - Unify entire image into seamless photorealistic result:\n\n"
                "CRITICAL CONTEXT:\n"
                "This image was created through multiple compositing steps (adding objects, inpainting, etc.).\n"
                "Your task: Make it look like ONE UNIFIED PHOTOGRAPH, not a collage.\n"
                "Remove ALL visible seams, color mismatches, lighting inconsistencies.\n\n"
                "COMMON PROBLEMS TO FIX:\n"
                "1. Objects have different color temperatures (some warm, some cool)\n"
                "2. Brightness mismatches between added objects and original scene\n"
                "3. Contrast differences (some areas too contrasty, others too flat)\n"
                "4. Shadow inconsistencies (direction or hardness doesn't match)\n"
                "5. Visible compositing edges or halos around objects\n"
                "6. Objects don't feel grounded in the scene\n"
                "7. Overall image lacks cohesion - looks like separate pieces\n\n"
                "YOUR TASK - PROFESSIONAL COLOR GRADING & UNIFICATION:\n"
                "STEP 1 - ANALYZE ENTIRE COMPOSITION:\n"
                "- Identify which areas look 'off' or disconnected\n"
                "- Find color temperature conflicts\n"
                "- Detect brightness/contrast mismatches\n"
                "- Look for unnatural edges or transitions\n\n"
                "STEP 2 - UNIFIED LIGHTING:\n"
                "- Establish ONE dominant light direction for entire scene\n"
                "- Make ALL objects respect this light direction\n"
                "- Unify shadow hardness across all elements\n"
                "- Add missing ambient occlusion between objects\n"
                "- Strengthen contact shadows where objects meet surfaces\n\n"
                "STEP 3 - COLOR HARMONY:\n"
                "- Choose ONE color temperature for the entire scene\n"
                "- Grade ALL objects to match this temperature\n"
                "- Create unified color palette - no outliers\n"
                "- Add subtle color spill between neighboring elements\n"
                "- Match saturation levels across all objects\n\n"
                "STEP 4 - CONTRAST & EXPOSURE:\n"
                "- Unify exposure - no objects too bright or too dark\n"
                "- Match contrast levels between all elements\n"
                "- Balance highlights and shadows across scene\n"
                "- Create cohesive tonal range\n\n"
                "STEP 5 - SEAMLESS INTEGRATION:\n"
                "- Blend ALL visible compositing edges\n"
                "- Remove halos, color fringing, or artifacts\n"
                "- Add atmospheric perspective if needed (distant = hazier)\n"
                "- Unify sharpness/blur across scene\n"
                "- Add subtle film grain or noise uniformly\n\n"
                "STEP 6 - GROUNDING & REALISM:\n"
                "- Ensure all objects cast appropriate shadows\n"
                "- Add reflections where needed (floors, mirrors, glossy surfaces)\n"
                "- Create subtle light bounce between objects\n"
                "- Add depth cues (foreground sharper, background softer)\n"
                "- Make everything feel 'heavy' and physically present\n\n"
                "REAL-WORLD EXAMPLE:\n"
                "BEFORE: Room with added furniture - chair too warm, table too bright, \n"
                "        plant has harsh shadows while room has soft shadows, visible edge around lamp\n"
                "AFTER FINALIZATION:\n"
                "  → ALL objects color-graded to match room's cool daylight\n"
                "  → Chair brightness reduced to match room exposure\n"
                "  → ALL shadows softened to match ambient lighting\n"
                "  → Lamp edge blended perfectly\n"
                "  → Added contact shadows under all furniture\n"
                "  → Slight color spill from wooden floor onto chair legs\n"
                "  → Unified film grain over entire image\n"
                "  → Result: Looks like ONE photograph, not composite\n\n"
                "CRITICAL SUCCESS CRITERIA:\n"
                "✅ Image looks like ONE unified photograph\n"
                "✅ ALL objects respect same lighting direction\n"
                "✅ Consistent color temperature throughout\n"
                "✅ Matched contrast and exposure across all elements\n"
                "✅ NO visible compositing edges or seams\n"
                "✅ Shadows are consistent (direction, hardness, color)\n"
                "✅ Every object feels grounded and physically present\n"
                "✅ Overall color harmony - no jarring mismatches\n"
                "✅ Professional photorealistic result\n"
                "CRITICAL RULES:\n"
                "❌ NEVER leave color temperature conflicts\n"
                "❌ NEVER ignore exposure mismatches\n"
                "❌ NEVER skip shadow unification\n"
                "❌ NEVER leave visible compositing edges\n"
                "❌ NEVER keep objects that look 'pasted on'\n"
                "❌ NEVER leave lighting direction conflicts\n\n"
                "REMEMBER:\n"
                "You are a PROFESSIONAL COLORIST doing final grade.\n"
                "This is the LAST STEP before client delivery.\n"
                "Make it PERFECT - unified, seamless, photorealistic.\n"
                "Goal: Viewer should NEVER suspect this was composited.\n"
            )
            return base_prompt

        if has_mask and has_reference:  # 有遮罩和参考图片
            base_prompt = (
                "🎯 CRITICAL: READ USER'S PROMPT FIRST!\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"USER'S INSTRUCTION (DO THIS EXACTLY!):\n"
                f'"{user_prompt}"\n'
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "YOUR TASK - SIMPLE AND DIRECT:\n"
                "1. Read user's prompt above - THIS IS WHAT YOU MUST DO!\n"
                "2. Look at IMAGE 1 (scene with sketch) - ERASE the sketch\n"
                "3. Look at IMAGE 2 (mask - colored area) - this is WHERE to place it\n"
                "4. Look at IMAGE OTHER (reference) - find the object user wants\n"
                "5. Place object from IMAGE OTHER into the colored area from IMAGE 1\n"
                "6. Follow user's prompt for HOW to place it (sitting/standing/facing/etc)\n"
                "7. Relight object to match scene lighting\n\n"
                "WHAT YOU HAVE:\n"
                "• IMAGE 1 (SCENE) = Where to add it (has colored sketch showing location)\n"
                "• IMAGE 2 (MASK) = Exact colored area for placement\n"
                "• IMAGES OTHER (REFERENCE) = The object user wants to add\n"
                "• USER PROMPT = Tells you WHAT and HOW\n\n"
                "CRITICAL RULES:\n"
                " RULE #1: USER'S PROMPT IS LAW - Follow it EXACTLY!\n"
                " RULE #2: Place object in colored area from IMAGE 2 (mask)\n"
                " RULE #3: ERASE sketch completely - replace with real object\n"
                " RULE #4: Relight object to match IMAGE 1 lighting\n\n"
                "SIMPLE EXAMPLE:\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "USER PROMPT: 'добавь мужчину на траве в обведённом кругу'\n"
                "\n"
                "WHAT YOU DO:\n"
                "1. Look at IMAGE 1 → find the man\n"
                "2. Look at IMAGE 3 → see the colored circle on grass\n"
                "3. Look at IMAGE 2 → see the sketch circle (erase it!)\n"
                "4. Place man from IMAGE 1 into circle area\n"
                "5. Make him ON THE GRASS (user said 'на траве')\n"
                "6. Erase colored circle sketch\n"
                "7. Relight man to match outdoor lighting\n"
                "8. Cast shadow on grass\n"
                "9. DONE - man is now on grass in that spot!\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "HOW TO DO IT:\n"
                "STEP 1 - READ USER PROMPT (at the top!):\n"
                "  → What object? (e.g., 'мужчину', 'chair', 'car')\n"
                "  → Where? (e.g., 'на траве', 'at desk', 'in corner')\n"
                "  → How? (e.g., 'standing', 'sitting', 'facing camera')\n\n"
                "STEP 2 - FIND OBJECT IN IMAGE 1:\n"
                "  → Identify the object user wants\n"
                "  → Remember its shape, textures, details\n"
                "  → Ignore its background\n\n"
                "STEP 3 - FIND LOCATION:\n"
                "  → IMAGE 2 (mask) shows colored area = exact spot\n"
                "  → IMAGE 1 shows sketch = rough guide (erase it!)\n\n"
                "STEP 4 - PLACE OBJECT:\n"
                "  → Put object in colored area (from IMAGE OTHER)\n"
                "  → Follow user's prompt (orientation, pose, etc.)\n"
                "  → ERASE sketch completely\n\n"
                "STEP 5 - MAKE IT REALISTIC:\n"
                "  → Relight object to match IMAGE 1's lighting\n"
                "  → Adjust colors to match scene\n"
                "  → Cast shadows (direction must match scene)\n"
                "  → Blend edges smoothly\n\n"
                "MORE EXAMPLES:\n"
                "Example 1 - 'Поставь этот стул в углу у окна':\n"
                "  → Find chair in IMAGE OTHER\n"
                "  → Place it in corner near window (colored area from IMAGE 1)\n"
                "  → Erase colored sketch\n"
                "  → Relight with window light\n"
                "  → Cast shadow\n"
                "  → DONE!\n\n"
                "Example 2 - 'Add this person sitting at the desk':\n"
                "  → Find person in IMAGE OTHER\n"
                "  → Place at desk (colored area)\n"
                "  → Make them SITTING (user said so!)\n"
                "  → Erase sketch\n"
                "  → Relight with office lights\n"
                "  → DONE!\n\n"
                "Example 3 - 'добавь мужчину на траве в обведённом кругу':\n"
                "  → Find man in IMAGE OTHER\n"
                "  → Place ON GRASS in circle area (IMAGE 1)\n"
                "  → Erase circle sketch\n"
                "  → Relight with outdoor lighting\n"
                "  → Cast shadow on grass\n"
                "  → DONE!\n\n"
                "WHAT YOU MUST DO:\n"
                "✅ Follow user's prompt EXACTLY\n"
                "✅ Place object in colored area (IMAGE 2)\n"
                "✅ ERASE sketch completely\n"
                "✅ Relight object to match scene\n"
                "✅ Cast shadows\n"
                "✅ Make it look photorealistic\n\n"
                "WHAT YOU MUST NOT DO:\n"
                "❌ NEVER ignore user's prompt\n"
                "❌ NEVER place object in wrong spot\n"
                "❌ NEVER keep sketch visible\n"
                "❌ NEVER forget shadows\n\n"
                "FINAL REMINDER:\n"
                "🔴 USER PROMPT (at top) = YOUR PRIMARY INSTRUCTION!\n"
                "🔴 Read it carefully and do EXACTLY what it says!\n"
            )
        elif has_mask:  # 有遮罩
            base_prompt = (
                "INPAINTING TASK - Replace sketch with photorealistic content:\n\n"
                "CONTEXT:\n"
                "User drew a rough SKETCH on their image to show where they want NEW content.\n"
                "The sketch is UGLY and TEMPORARY - it's just a guide.\n"
                "Your job: ERASE the sketch, CREATE beautiful realistic content in that spot.\n\n"
                "IMAGE 1 (PHOTO WITH SKETCH OVERLAY):\n"
                "- Original photo/render with user's sketch drawn on top\n"
                "- Sketch colors show LOCATION and rough SHAPE only\n"
                "- Sketch is NOT the final look - it will be DELETED\n\n"
                "IMAGE 2 (MASK - WHERE TO EDIT):\n"
                "- Black areas = DON'T TOUCH (keep original)\n"
                "- Colored areas = SKETCH LOCATION (delete sketch, add new content)\n\n"
                "STEP-BY-STEP PROCESS:\n"
                "1. Look at IMAGE 1 - see WHERE the sketch is\n"
                "2. Look at IMAGE 2 - see the ugly sketch user drew\n"
                "3. Read user's PROMPT - understand WHAT to create\n"
                "4. COMPLETELY ERASE the sketch from those areas\n"
                "5. CREATE photorealistic content matching the prompt\n"
                "6. Match original image's lighting, shadows, perspective, style\n"
                "7. Blend edges perfectly (no visible seams)\n\n"
                "REAL EXAMPLES:\n"
                "Example 1:\n"
                "  - User draws RED CIRCLE\n"
                "  - Prompt: 'add sunset light through window'\n"
                "  - You do: DELETE red circle → CREATE realistic warm sunlight rays\n"
                "  - Final: Beautiful sunset light, NO red circle visible\n\n"
                "Example 2:\n"
                "  - User draws BLUE BLOB\n"
                "  - Prompt: 'add water puddle on floor'\n"
                "  - You do: DELETE blue blob → CREATE realistic water with reflections\n"
                "  - Final: Real water puddle, NO blue blob visible\n\n"
                "Example 3:\n"
                "  - User draws GREEN SCRIBBLES\n"
                "  - Prompt: 'add plant in vase'\n"
                "  - You do: DELETE green scribbles → CREATE detailed plant with leaves\n"
                "  - Final: Beautiful plant, NO scribbles visible\n\n"
                "CRITICAL RULES:\n"
                "❌ NEVER keep the sketch visible\n"
                "❌ NEVER 'improve' the sketch - DELETE it completely\n"
                "❌ NEVER leave construction lines, rough shapes, or color blobs\n"
                "✅ ALWAYS erase sketch 100% before creating new content\n"
                "✅ ALWAYS create photorealistic result\n"
                "✅ ALWAYS match original image lighting and style\n"
                "✅ ALWAYS blend seamlessly at edges\n"
                "✅ ALWAYS follow user's text prompt for WHAT to create\n\n"
                "REMEMBER:\n"
                "Sketch = temporary guide (like construction lines in drawing)\n"
                "Final image = professional result with NO sketch traces\n"
                "User drew sketch to show LOCATION + rough IDEA\n"
                "You create PHOTOREALISTIC version and REMOVE sketch completely\n"
            )
        elif has_reference:  # 有参考图片
            base_prompt = (
                "PHOTOREALISTIC OBJECT INTEGRATION - Seamlessly blend reference into scene:\n\n"
                "CRITICAL CONTEXT:\n"
                "User is NOT asking for simple copy-paste! They want PHOTOREALISTIC INTEGRATION.\n"
                "The object from reference must look like it was PHOTOGRAPHED in the target scene.\n"
                "This requires ADVANCED color grading, lighting match, shadow casting, and perspective correction.\n\n"
                "IMAGE 1 (TARGET SCENE - DESTINATION):\n"
                "- This is your PRIMARY reference for visual style\n"
                "- Analyze: lighting direction, color temperature, shadow hardness, ambient light\n"
                "- The object from IMAGE 1 must MATCH this scene's lighting 100%\n\n"
                "IMAGE OTHER (REFERENCE - SOURCE OBJECT):\n"
                "- Contains the object/person to integrate into IMAGE 1\n"
                "- Extract its SHAPE and STRUCTURE (what it is)\n"
                "- IGNORE its original lighting, colors, and background\n"
                "- Think: 'I need this OBJECT, but I'll RELIGHT it for the new scene'\n\n"
                "YOUR TASK - PROFESSIONAL COMPOSITING:\n"
                "STEP 1 - LIGHTING ANALYSIS (IMAGE 1):\n"
                "- Light direction: Where are shadows pointing? (e.g., left side, top-right)\n"
                "- Light hardness: Sharp shadows = hard light, soft shadows = diffuse light\n"
                "- Color temperature: Warm (orange/yellow) or cool (blue/white)?\n"
                "- Ambient light: How bright are shadow areas?\n"
                "- Reflections: Are there glossy surfaces? What do they reflect?\n\n"
                "STEP 2 - OBJECT EXTRACTION (IMAGE OTHER):\n"
                "- Identify the object shape, structure, materials\n"
                "- Forget its current lighting - you will RELIGHT it\n"
                "- Preserve textures and material properties (metal, wood, fabric, etc.)\n\n"
                "STEP 3 - INTEGRATION (CRITICAL!):\n"
                "A. RELIGHTING:\n"
                "   - Apply IMAGE 1's light direction to the object\n"
                "   - Match light color temperature exactly\n"
                "   - Create shadows that match IMAGE 1's shadow style\n"
                "   - Add ambient occlusion in contact areas\n"
                "B. COLOR GRADING:\n"
                "   - Adjust object's colors to match IMAGE 1's color palette\n"
                "   - If IMAGE 1 is warm → warm the object's colors\n"
                "   - If IMAGE 1 is desaturated → reduce object's saturation\n"
                "   - Match overall brightness/exposure\n"
                "C. SHADOWS:\n"
                "   - Cast shadows from object onto IMAGE 1's surfaces\n"
                "   - Shadow direction MUST match IMAGE 1's existing shadows\n"
                "   - Shadow softness MUST match IMAGE 1's shadow hardness\n"
                "   - Add contact shadows (dark areas where object touches surface)\n"
                "D. PERSPECTIVE:\n"
                "   - Match camera angle from IMAGE 1\n"
                "   - Scale object appropriately for scene\n"
                "   - Ensure ground plane alignment\n"
                "E. REFLECTIONS & AMBIENT:\n"
                "   - If object is glossy → reflect IMAGE 1's environment\n"
                "   - Add ambient light bounce from IMAGE 1's surfaces\n"
                "   - Color spill: nearby colored surfaces affect object colors\n\n"
                "STEP 4 - FINAL BLEND:\n"
                "- Edge softness: match IMAGE 1's sharpness/blur\n"
                "- Atmospheric perspective: distant objects are hazier\n"
                "- Depth of field: match IMAGE 1's focus plane\n"
                "- Film grain/noise: match IMAGE 1's texture\n\n"
                "REAL-WORLD EXAMPLE:\n"
                "IMAGE 1: Dark moody interior with warm tungsten lights from left\n"
                "IMAGE 2: Photo of a red chair (photographed outdoors, bright daylight)\n"
                "USER: 'Add the chair by the window'\n"
                "WRONG (copy-paste): Bright red chair with daylight look = looks fake!\n"
                "RIGHT (professional integration):\n"
                "  → Chair shape preserved\n"
                "  → BUT relit with warm tungsten light from left\n"
                "  → Red color adjusted to warm/darker tone matching room\n"
                "  → Soft shadow cast to the right (opposite of light)\n"
                "  → Contact shadow under chair legs (ambient occlusion)\n"
                "  → Slight warm color spill from wooden floor onto chair base\n"
                "  → Chair looks like it was PHOTOGRAPHED in this room\n\n"
                "CRITICAL SUCCESS CRITERIA:\n"
                "✅ Object MUST look like it was PHOTOGRAPHED in IMAGE 1's scene\n"
                "✅ Lighting on object MUST match IMAGE 1 exactly (direction, color, hardness)\n"
                "✅ Object colors MUST be color-graded to match IMAGE 1's palette\n"
                "✅ Shadows MUST be cast correctly with right direction and softness\n"
                "✅ No visible compositing edges - perfect blend\n"
                "✅ Viewer should NOT be able to tell it's from different photo\n"
                "CRITICAL MISTAKES TO AVOID:\n"
                "❌ NEVER keep object's original lighting from IMAGE OTHER\n"
                "❌ NEVER keep object's original colors unchanged\n"
                "❌ NEVER forget to cast shadows onto IMAGE 1's surfaces\n"
                "❌ NEVER ignore IMAGE 1's light direction\n"
                "❌ NEVER make it look like a PNG sticker pasted on\n"
                "❌ NEVER create lighting conflicts (e.g., shadows wrong direction)\n\n"
                "REMEMBER:\n"
                "You are a PROFESSIONAL COMPOSITOR, not a copy-paste tool.\n"
                "The object must be RELIT, COLOR-GRADED, and SHADOWED to match the target scene.\n"
                "Final result should be INDISTINGUISHABLE from a real photograph.\n"
                "OLD STYLE TRANSFER PROMPT (for reference, DON'T use this):\n"
                "You are receiving TWO images:\n\n"
                "IMAGE 1 (Original Image - ONLY for composition):\n"
                "- Use EXCLUSIVELY for object positions, layout, scene structure\n"
                "- IGNORE its colors, materials, lighting, and current style\n"
                "- Treat current look as TEMPORARY - will be completely replaced\n"
                "- Keep ONLY the composition, everything else changes\n\n"
                "IMAGE OTHER (Style Reference - YOUR PRIMARY GUIDE):\n"
                "- This is your MAIN reference for ALL visual aspects\n"
                "- COPY AGGRESSIVELY: lighting setup, material types, color palette, texture quality, mood, atmosphere\n"
                "- Study this image's visual language and REPLICATE it completely\n"
                "- This shows the TARGET result you must achieve\n\n"
                "YOUR TASK - AGGRESSIVE STYLE TRANSFORMATION:\n"
                "1. Keep ONLY composition/layout/objects from IMAGE 1\n"
                "2. COMPLETELY REPLACE materials with IMAGE OTHER style:\n"
                "   - If IMAGE OTHER has metallic materials → make IMAGE 1's objects metallic\n"
                "   - If IMAGE OTHER has matte surfaces → make IMAGE 1's objects matte\n"
                "   - If IMAGE OTHER has wood texture → apply wood-like materials\n"
                "3. COMPLETELY REPLACE lighting with IMAGE OTHER setup:\n"
                "   - Match light direction, intensity, color temperature\n"
                "   - Copy shadow hardness/softness\n"
                "   - Replicate ambient lighting mood\n"
                "4. COMPLETELY REPLACE colors with IMAGE OTHER palette:\n"
                "   - If IMAGE OTHER is warm (orange/red) → make IMAGE 1 warm\n"
                "   - If IMAGE OTHER is cool (blue/cyan) → make IMAGE 1 cool\n"
                "   - Match color saturation and vibrancy\n"
                "5. REPLICATE atmosphere and mood:\n"
                "   - If IMAGE OTHER is dramatic → make IMAGE 1 dramatic\n"
                "   - If IMAGE OTHER is soft/gentle → make IMAGE 1 soft/gentle\n"
                "   - Copy depth, detail level, visual complexity\n\n"
                "CRITICAL - BE AGGRESSIVE, NOT CONSERVATIVE:\n"
                "❌ DON'T just 'slightly adjust' IMAGE 1\n"
                "❌ DON'T preserve IMAGE 1's current colors/materials\n"
                "❌ DON'T be subtle or gentle with changes\n"
                "✅ COMPLETELY TRANSFORM to match IMAGE OTHER style\n"
                "✅ Think: 'IMAGE OTHER is the goal, IMAGE 1 is just a layout template'\n"
                "✅ If IMAGE OTHER is blue but IMAGE 1 is red → make it BLUE\n"
                "✅ If IMAGE OTHER is dark but IMAGE 1 is bright → make it DARK\n"
                "✅ If IMAGE OTHER is detailed but IMAGE 1 is simple → add DETAILS\n\n"
                "EXAMPLE:\n"
                "- IMAGE 1: Cool blue render with flat lighting\n"
                "- IMAGE OTHER: Warm sunset photo with golden light, soft shadows, rich textures\n"
                "- YOUR RESULT: Keep IMAGE 1's objects/layout BUT with:\n"
                "  → Golden sunset lighting from IMAGE OTHER\n"
                "  → Warm orange/red colors from IMAGE OTHER\n"
                "  → Soft shadows and rich textures from IMAGE OTHER\n"
                "  → Final looks like IMAGE OTHER style applied to IMAGE 1's composition\n\n"
                "REMEMBER:\n"
                "Original image (IMAGE 1) = composition template ONLY\n"
                "Style reference (IMAGE OTHER) = your visual TARGET\n"
                "AGGRESSIVELY copy IMAGE OTHER visual style to IMAGE 1's layout\n"
            )
        else:
            # 没有遮罩也没有参考图片,只有提示词输入的基本提示词
            base_prompt = (
                "You are REFINING and IMPROVING an existing image:\n\n"
                "ORIGINAL IMAGE:\n"
                "- This is the base image you'll improve\n"
                "- Keep main composition, subjects, layout\n\n"
                "YOUR TASK:\n"
                "1. Understand current image\n"
                "2. Apply user's improvement instructions\n"
                "3. Keep overall composition intact\n"
                "4. Make changes feel natural and cohesive\n"
                "5. Enhance quality while preserving intent\n"
            )
        if user_prompt.strip():
            return f"{base_prompt}\n\nUSER'S EDIT INSTRUCTIONS:\n{user_prompt.strip()}"
        else:
            return base_prompt

    def _edit_with_rest(
        self,
        image_path: str,
        prompt: str,
        mask_path: str = None,
        reference_path: str = None,
        width: int = 0,
        height: int = 0,
        aspect_ratio: str = "1:1",
    ) -> Tuple[bytes, str]:
        """
        图片顺序很重要
        IMAGE 1 (scene with sketch)
        IMAGE 2 (mask - colored area)
        IMAGE OTHER (reference)
        """
        try:
            #
            # 对于风格转换, 最先放入 Reference
            parts = [{"text": prompt}]

            def add_part(image_file_path):
                with open(image_file_path, "rb") as f:
                    image_base64 = base64.b64encode(f.read()).decode("utf-8")
                part = {"inline_data": {"mime_type": "image/png", "data": image_base64}}
                parts.append(part)

            add_part(image_path)  # 添加主图
            # 添加遮罩
            if mask_path:
                add_part(mask_path)
            if reference_path:
                if isinstance(reference_path, list):
                    for ref_path in reference_path:
                        add_part(ref_path)
                else:
                    add_part(reference_path)
            url = f"{self.base_url}/{self.model}:generateContent"
            headers = {
                "x-goog-api-key": self.api_key,
                "Content-Type": "application/json",
                "X-Goog-Api-Client": "python-blender-addon",
            }
            # Determine resolution
            resolution_str = "1K"
            if width > 0 and height > 0:
                # User forced resolution
                if width >= 4096 or height >= 4096:
                    resolution_str = "4K"
                elif width >= 2048 or height >= 2048:
                    resolution_str = "2K"
            payload = {
                "contents": [{"parts": parts}],
                "generationConfig": {
                    "temperature": 0.7,  # Lower temperature for more faithful edits
                    "maxOutputTokens": 32768,
                    "candidateCount": 1,
                    "responseModalities": ["TEXT", "IMAGE"],
                    "imageConfig": {
                        "imageSize": resolution_str,
                        "aspectRatio": aspect_ratio,
                    },
                },
            }
            response = requests.post(url, headers=headers, json=payload, timeout=300)
            if response.status_code != 200:
                raise GeminiAPIError(f"Edit request failed: {response.status_code} - {response.text}")
            # Parse response (same as generate_with_rest)
            result = response.json()
            if "candidates" not in result or not result["candidates"]:
                raise GeminiAPIError("No candidates in edit response")
            parts = result["candidates"][0]["content"]["parts"]
            # Find image part
            for part in parts:
                inline_data_key = "inline_data" if "inline_data" in part else "inlineData" if "inlineData" in part else None
                if not inline_data_key:
                    continue
                inline_data = part[inline_data_key]
                data_key = "data" if "data" in inline_data else "bytes" if "bytes" in inline_data else None
                if data_key and inline_data[data_key]:
                    image_data = base64.b64decode(inline_data[data_key])
                    mime_type = inline_data.get("mime_type", inline_data.get("mimeType", "image/png"))
                    return image_data, mime_type
            raise GeminiAPIError("No image found in edit response")
        except requests.RequestException as e:
            raise GeminiAPIError(f"Network error during edit: {str(e)}")
        except Exception as e:
            if isinstance(e, GeminiAPIError):
                raise
            raise GeminiAPIError(f"Edit failed: {str(e)}")
