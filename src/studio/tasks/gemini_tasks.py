import time
from pathlib import Path
from typing import Optional

from ..providers import GeminiProvider, GeminiImageGenerateProvider, AccountGeminiImageProvider, GeminiImageEditProvider
from ..providers.gemini.config import GeminiImageEditPayload, GeminiImageGeneratePayload
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
        self.provider: GeminiProvider = None

    def prepare(self) -> bool:
        """准备 API 客户端"""
        try:
            # 验证 API Key
            if not self.api_key or not self.api_key.strip():
                self.update_progress(0, "API Key 未设置")
                raise Exception("API Key Not Set")
            # 创建 API 客户端
            self.provider = GeminiProvider(self.api_key)
            self.update_progress(0, "API 客户端已准备")
            return True
        except Exception as e:
            self.update_progress(0, f"准备失败: {str(e)}")
            raise e

    def cleanup(self) -> None:
        """清理资源"""
        self.provider = None

    def _validate_image_path(self, image_path: str, param_name: str = "图片") -> bool:
        """
        验证图片路径

        Args:
            image_path: 图片路径
            param_name: 参数名称（用于错误提示）

        Returns:
            是否有效
        """
        path = Path(image_path)
        if not path.exists():
            self.update_progress(message=f"{param_name}不存在: {image_path}")
            return False

        if not path.is_file():
            self.update_progress(message=f"{param_name}不是文件: {image_path}")
            return False

        # 检查文件大小（可选）
        file_size = path.stat().st_size
        max_size = 30 * 1024 * 1024  # 30MB
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
        resolution: str = "1K",
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
        self.resolution = resolution
        self.width = width
        self.height = height
        self.aspect_ratio = aspect_ratio

        # 设置总步骤数
        self.progress.total_steps = 4

    def prepare(self) -> bool:
        """准备任务"""
        if not super().prepare():
            return False
        self.provider = GeminiImageGenerateProvider(self.api_key)
        # 验证输入图片
        if self.image_path and not self._validate_image_path(self.image_path, "输入图片"):
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
                return TaskResult.failure_result(Exception("Task Cancelled"), error_msg)
            self.update_progress(2, "正在调用 Gemini API...")

            # 调用 API
            image_data, mime_type = b"", "image/png"
            payload = GeminiImageGeneratePayload(
                image_path=self.image_path,
                user_prompt=self.user_prompt,
                reference_images_path=self.reference_images_path,
                is_color_render=self.is_color_render,
                width=self.width,
                height=self.height,
                aspect_ratio=self.aspect_ratio,
            )
            image_data, mime_type = self.provider.generate_image(payload)

            if self.is_cancelled():
                error_msg = "生成失败: 任务被取消"
                self.update_progress(message=error_msg)
                return TaskResult.failure_result(Exception("Task Cancelled"), error_msg)

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
                return TaskResult.failure_result(Exception("Task Cancelled"), error_msg)

            self.update_progress(4, "图片生成完成")

            return TaskResult.success_result(
                data=result_data,
                metadata={
                    "prompt": self.user_prompt,
                    "is_color_render": self.is_color_render,
                    "resolution": self.resolution,
                    "width": self.width,
                    "height": self.height,
                    "aspect_ratio": self.aspect_ratio,
                    "has_reference": bool(self.reference_images_path),
                },
            )

        except Exception as e:
            error_msg = f"图片生成失败: {str(e)}"
            self.update_progress(message=error_msg)
            return TaskResult.failure_result(e, error_msg)


class AccountGeminiImageGenerateTask(GeminiImageGenerationTask):
    def prepare(self) -> bool:
        if not super().prepare():
            return False
        self.provider = AccountGeminiImageProvider(self.api_key)
        return True


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

        self.provider = GeminiImageEditProvider(self.api_key)

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
            payload = GeminiImageEditPayload(
                image_path=self.image_path,
                edit_prompt=self.edit_prompt,
                mask_path=self.mask_path,
                reference_image_path=self.reference_images_path,
                resolution=self.resolution,
                aspect_ratio=self.aspect_ratio,
            )
            image_data, mime_type = self.provider.generate_image(payload)

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
            image_data, mime_type = self.provider.generate_image(
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
