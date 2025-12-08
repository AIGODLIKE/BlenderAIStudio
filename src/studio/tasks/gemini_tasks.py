import base64
import json
import tempfile
import time
from pathlib import Path
from typing import Tuple, Optional

import OpenImageIO as oiio
import numpy as np
import requests

from .task import Task, TaskResult
from .prompt import *


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
            time.sleep(1)
            if self.is_cancelled():
                error_msg = "生成失败: 任务被取消"
                self.update_progress(message=error_msg)
                return TaskResult.failure_result(Exception("任务被取消"), error_msg)
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

            if self.is_cancelled():
                error_msg = "生成失败: 任务被取消"
                self.update_progress(message=error_msg)
                return TaskResult.failure_result(Exception("任务被取消"), error_msg)

            self.update_progress(3, "API 调用成功，处理响应...")

            # 构建结果
            result_data = {
                "image_data": image_data,
                "mime_type": mime_type,
                "width": self.width,
                "height": self.height,
            }

            if self.is_cancelled():
                error_msg = "生成失败: 任务被取消"
                self.update_progress(message=error_msg)
                return TaskResult.failure_result(Exception("任务被取消"), error_msg)

            self.update_progress(4, "图片生成完成")

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
            resolution: str = "1K",
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
        self.resolution = resolution
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
                resolution=self.resolution,
                aspect_ratio=self.aspect_ratio,
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
            resolution="1K",
            aspect_ratio="1:1",
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
        self.resolution = resolution
        self.aspect_ratio = aspect_ratio
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
                resolution=self.resolution,
                aspect_ratio=self.aspect_ratio,
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
            resolution: str = "1K",
            aspect_ratio: str = "1:1",
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
        :param aspect_ratio:
        :param image_path:
        :param edit_prompt:
        :param mask_path:
        :param reference_image_path:
        :param resolution:
        """
        try:
            # Build edit prompt
            full_prompt = self._build_edit_prompt(
                edit_prompt,
                has_mask=bool(mask_path),
                has_reference=bool(reference_image_path),
            )
            return self._edit_with_rest(image_path, full_prompt, mask_path, reference_image_path, resolution,
                                        aspect_ratio)

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

        if user_prompt == "[智能修复]":  # 智能修复的提示词
            base_prompt =EDIT_SMART_REPAIR
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

    def _edit_with_rest(
            self,
            image_path: str,
            prompt: str,
            mask_path: str = None,
            reference_path: str = None,
            resolution="1K",
            aspect_ratio: str = "1:1",
    ) -> Tuple[bytes, str]:
        """
        图片顺序很重要
        IMAGE 1 (scene with sketch)
        IMAGE 2 (mask - colored area)
        IMAGE OTHER (reference)
        """
        try:
            parts = [{"text": prompt}]

            def add_part(image_file_path):
                with open(image_file_path, "rb") as f:
                    image_base64 = base64.b64encode(f.read()).decode("utf-8")
                part = {"inline_data": {"mime_type": "image/png", "data": image_base64}}
                parts.append(part)
                print("add_part", image_file_path)

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
            payload = {
                "contents": [{"parts": parts}],
                "generationConfig": {
                    "temperature": 0.7,  # Lower temperature for more faithful edits
                    "maxOutputTokens": 32768,
                    "candidateCount": 1,
                    "responseModalities": ["TEXT", "IMAGE"],
                    "imageConfig": {
                        "imageSize": resolution,
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
