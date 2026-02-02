from typing import Dict, Any
from .base import InputProcessor, CancelledError
from ...utils.render import BlenderRenderHelper
from ...logger import logger


class RenderProcessor(InputProcessor):
    """Blender 渲染输入处理器

    职责：
    - 根据配置渲染 Blender 场景
    - 支持多种渲染类型（彩色、深度等）
    - 支持取消渲染
    - 管理临时文件

    线程安全：
    - 运行在 Task 子线程中
    - 取消方法是线程安全的
    """

    def __init__(self):
        """初始化渲染处理器"""
        self.render_helper = BlenderRenderHelper()
        self._cancel_flag = False

    def process(self, params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """处理 Blender 渲染输入

        从 params 中提取渲染配置，执行渲染，返回渲染结果路径。

        Args:
            params: 输入参数字典，支持的键：
                - input_type: str - 渲染类型
                    - "CameraRender": 渲染彩色图像
                    - "CameraDepth": 渲染深度图
                    - "FastRender": 快速渲染
                    - "NoInput": 不渲染
                - camera: 相机名称
                - render_samples: int - 采样数（可选）
                - render_resolution: tuple - 分辨率（可选）
            context: 上下文字典

        Returns:
            dict: 渲染结果，包含：
                - image_path: str - 渲染图片的文件路径（如果渲染了）

        Raises:
            ValueError: 参数无效（如未知的 input_type）
            RuntimeError: 渲染失败
            CancelledError: 渲染被取消
        """
        # 重置取消标志
        self._cancel_flag = False

        # 提取渲染类型
        input_type = params.get("input_type", "NoInput")

        # 如果不需要渲染，直接返回
        if input_type == "NoInput":
            return {"image_path": ""}

        # 验证渲染类型
        if input_type not in ["CameraRender", "CameraDepth", "FastRender"]:
            raise ValueError(f"Not supported input type: {input_type}.")

        # 检查取消
        if self._cancel_flag:
            raise CancelledError("Render Canceled")

        # 执行渲染
        logger.info(f"RenderProcessor: Render Started ({input_type})")
        try:
            image_path = self.render_helper.render(input_type, context)

            # 检查取消
            if self._cancel_flag:
                logger.info("RenderProcessor: Render Canceled")
                raise CancelledError("Render Canceled")

            logger.info(f"RenderProcessor: Render Completed -> {image_path}")
            return {"image_path": image_path}
        except CancelledError:
            raise
        except Exception as e:
            logger.error(f"RenderProcessor: Render Failed -> {e}")
            raise RuntimeError(f"Render Failed: {e}") from e

    def cancel(self) -> None:
        """取消渲染

        设置取消标志，通知 BlenderRenderHelper 停止渲染。

        线程安全：可以从任何线程调用。
        """
        logger.info("RenderProcessor: 收到取消请求")
        self._cancel_flag = True
        self.render_helper.cancel()

    def cleanup(self) -> None:
        """清理资源

        BlenderRenderHelper 的临时文件由系统管理，这里不需要额外清理。
        """
        # BlenderRenderHelper 使用 tempfile.NamedTemporaryFile(delete=False)
        # 临时文件会在适当的时候被系统清理
        pass
