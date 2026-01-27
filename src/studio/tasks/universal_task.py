from traceback import print_exc
from typing import Dict, Any, Optional

from .task import Task, TaskResult
from ..config.model_registry import ModelRegistry
from ..providers import UniversalProvider
from ..input_processors import InputProcessorRegistry, InputProcessor, CancelledError
from ...logger import logger


class UniversalModelTask(Task):
    """通用模型任务

    根据模型配置动态创建任务，无需为每个模型编写单独的 Task 类。

    **职责：**
    - 接收已构建好的参数
    - 验证参数
    - 执行 API 调用
    - 处理响应结果
    - 创建历史记录
    """

    def __init__(self, model_id: str, auth_mode: str, credentials: Dict[str, str], params: Dict[str, Any], context: dict, task_name: Optional[str] = None):
        """初始化通用模型任务

        Args:
            model_id: 模型 ID（在 models_config.json 中定义）
            auth_mode: 认证模式
            credentials: 认证凭证，如 {"api_key": "xxx"} 或 {"token": "xxx"}
            params: 任务参数字典（原始参数，由 InputProcessor 和 RequestBuilder 处理）
            context: 上下文字典
            task_name: 任务名称（可选，默认使用模型名称）

        Raises:
            ValueError: 如果模型不存在或参数无效
        """
        # 获取模型配置
        self.model_config = ModelRegistry.get_instance().get_model_by_id(auth_mode, model_id)
        self.model_id = model_id

        # 设置任务名称
        task_name = task_name or f"{self.model_config.model_name}"
        super().__init__(task_name)

        self.auth_mode = auth_mode
        self.credentials = credentials
        self.params = params
        self.context = context
        self.provider: UniversalProvider = None
        self.input_processors: Dict[str, InputProcessor] = {}  # 存储按 processor 分组的处理器

        # 设置总步骤数
        self.progress.total_steps = 4

    def cancel(self) -> bool:
        """取消任务

        取消所有 InputProcessor 和 Provider。
        """
        # 取消所有 InputProcessor
        for processor in self.input_processors.values():
            try:
                processor.cancel()
            except Exception as e:
                logger.error(f"取消 InputProcessor 失败: {e}")
        return super().cancel()

    def prepare(self) -> bool:
        """准备任务

        执行流程：
        1. 处理输入参数（使用 InputProcessor）
        2. 验证认证模式
        3. 验证必需参数
        4. 创建 Provider 实例

        Returns:
            准备成功返回 True，失败返回 False
        """
        try:
            # 1. 处理输入参数（使用 InputProcessor）
            self.update_progress(1, "准备输入数据...")
            processor_groups = self._group_params_by_processor()

            for (processor_name, group_name), input_params in processor_groups.items():
                if not input_params:
                    continue

                # 检查取消
                if self.is_cancelled():
                    return False

                # 为每个 (processor, group) 组合创建独立的实例
                # 这样同一个 processor 可以被多次调用
                processor_key = f"{processor_name}:{group_name}"
                if processor_key not in self.input_processors:
                    self.input_processors[processor_key] = InputProcessorRegistry.get(processor_name)

                processor = self.input_processors[processor_key]

                # 执行输入处理
                logger.info(f"执行 InputProcessor: {processor_name} (group: {group_name})")
                try:
                    result = processor.process(input_params, self.context)

                    # 应用 output_mapping
                    # 从 input_processors 配置中获取 output_mapping
                    input_processors_config = self.model_config.input_processors
                    output_mapping = {}
                    for proc_config in input_processors_config:
                        if proc_config.get("processor") == processor_name and proc_config.get("group", "default") == group_name:
                            output_mapping = proc_config.get("output_mapping", {})
                            break

                    # 应用映射
                    mapped_result = self._apply_output_mapping(result, output_mapping)

                    # 合并映射后的结果到参数中
                    self.params.update(mapped_result)

                    logger.info(f"InputProcessor {processor_name}:{group_name} 完成，映射结果: {mapped_result}")
                except CancelledError:
                    logger.info(f"InputProcessor {processor_name}:{group_name} 被取消")
                    return False

            # 清理所有已处理的输入参数（在所有处理器完成后统一清理）
            # TODO 添加是否需要清理的配置项
            # input_processors_config = self.model_config.input_processors
            # for proc_config in input_processors_config:
            #     input_mapping = proc_config.get("input_mapping", {})
            #     for user_param in input_mapping.values():
            #         self.params.pop(user_param, None)

            # 检查取消
            if self.is_cancelled():
                return False

            # 2. 创建 Provider
            self.provider = UniversalProvider(
                model_config=self.model_config,
                auth_mode=self.auth_mode,
                credentials=self.credentials,
                task_id=self.task_id,
            )

            # 3. 验证认证模式
            if not self.model_config.supports_auth_mode(self.auth_mode):
                self.update_progress(0, f"模型不支持 {self.auth_mode} 模式")
                return False

            # 4. 验证必需参数
            if not self._validate_parameters():
                return False

            self.update_progress(2, "准备完成")
            return True

        except Exception as e:
            self.update_progress(0, f"任务准备失败: {str(e)}")
            logger.error(f"任务准备失败: {e}")
            return False

    def _apply_output_mapping(self, result: Dict[str, Any], output_mapping: Dict[str, str]) -> Dict[str, Any]:
        """应用输出映射

        Args:
            result: 处理器返回的原始结果，如 {"image_path": "/tmp/render.png"}
            output_mapping: 输出映射配置，如 {"image_path": "main_image"}

        Returns:
            映射后的结果，如 {"main_image": "/tmp/render.png"}
        """
        if not output_mapping:
            # 没有映射配置，返回原始结果
            return result

        mapped_result = {}

        # 应用映射
        for original_key, mapped_key in output_mapping.items():
            if original_key in result:
                mapped_result[mapped_key] = result[original_key]

        # 处理未映射的字段（保持原名）
        for key, value in result.items():
            if key not in output_mapping:
                mapped_result[key] = value

        return mapped_result

    def _group_params_by_processor(self) -> Dict[tuple, Dict[str, Any]]:
        """按 input_processors 配置分组参数

        从模型配置的 input_processors 字段读取处理器配置，
        按照 input_mapping 提取参数。

        配置结构：
        {
            "input_processors": [
                {
                    "processor": "RenderProcessor",
                    "group": "main_image",
                    "input_mapping": {
                        "input_type": "input_image_type",  // 处理器参数 <- 用户参数
                        "camera": "input_camera"
                    },
                    "output_mapping": {
                        "image_path": "main_image"  // 原始输出 -> 映射输出
                    }
                }
            ]
        }

        Returns:
            dict: {(processor_name, group_name): {处理器参数名: 参数值}}
        """
        groups = {}

        # 从 model_config 获取 input_processors 配置
        input_processors_config = self.model_config.input_processors

        for processor_config in input_processors_config:
            processor_name = processor_config.get("processor")
            group_name = processor_config.get("group", "default")
            input_mapping = processor_config.get("input_mapping", {})

            if not processor_name:
                continue

            # 使用 (processor, group) 元组作为 key
            key = (processor_name, group_name)
            groups[key] = {}

            # 按照 input_mapping 提取参数
            # input_mapping: {"input_type": "input_image_type", "camera": "input_camera"}
            # 处理器参数名 <- 用户参数名
            for processor_param, user_param in input_mapping.items():
                if user_param in self.params:
                    groups[key][processor_param] = self.params[user_param]

        return groups

    def execute(self) -> TaskResult:
        """执行任务

        Returns:
            TaskResult 对象
        """
        try:
            self.update_progress(3, "正在调用 API...")

            # 检查取消
            if self.is_cancelled():
                return TaskResult.failure_result(Exception("Task Cancelled"), "任务在执行前被取消")

            # 调用 Provider 执行请求（通用方法）
            parsed_data = self.provider.execute(self.params)
            # 格式校验
            self._validate_result_data_format(parsed_data)
            # 检查取消
            if self.is_cancelled():
                return TaskResult.failure_result(Exception("Task Cancelled"), "任务在执行过程中被取消")

            self.update_progress(4, "API 调用成功，处理响应...")

            self.update_progress(4, f"任务: {self.task_name} 完成")

            # 创建元数据
            metadata = {
                "model_id": self.model_id,
                "model_name": self.model_config.model_name,
                "category": self.model_config.category,
                "auth_mode": self.auth_mode,
                "params": self.params,
                "task_id": self.task_id,
            }

            return TaskResult.success_result(data=parsed_data, metadata=metadata)

        except Exception as e:
            print_exc()
            error_msg = f"任务: {self.task_name} 执行失败 -> {str(e)}"
            self.update_progress(message=error_msg)
            return TaskResult.failure_result(e, error_msg)

    def cleanup(self) -> None:
        """清理资源"""
        # 清理所有 InputProcessor
        for processor in self.input_processors.values():
            try:
                processor.cleanup()
            except Exception as e:
                logger.error(f"清理 InputProcessor 失败: {e}")

        self.input_processors.clear()
        self.provider = None

    def _validate_parameters(self) -> bool:
        """验证参数

        检查模型配置中定义的必需参数是否都已提供。

        Returns:
            验证通过返回 True，否则返回 False
        """
        # 获取所有必需参数
        required_params = []
        for param_def in self.model_config.parameters:
            if param_def.get("required", False):
                required_params.append(param_def["name"])

        # 检查缺失的参数
        missing_params = [p for p in required_params if p not in self.params]

        if missing_params:
            self.update_progress(0, f"缺少参数: {', '.join(missing_params)}")
            return False

        return True

    def _validate_result_data_format(self, parsed_data: list[tuple[str, str | bytes]]):
        """验证结果数据格式

        检查响应数据是否包含必要的键。
        Args:
            parsed_data: 处理后的响应数据，每个元素为 (mime_type, data) 元组
        Raises:
            ValueError: 如果响应数据格式不正确
            TypeError: 如果响应数据类型不正确
        """
        if not isinstance(parsed_data, list):
            raise ValueError("Output data must be a list")
        if len(parsed_data) == 0:
            raise ValueError("Output data cannot be empty")
        for output in parsed_data:
            if not isinstance(output, (tuple, list)) or len(output) != 2:
                raise TypeError("Output must contain two elements (mime, data)")
            if not isinstance(output[0], str):
                raise TypeError("Output mime type must be a string")
            if not isinstance(output[1], (str, bytes)):
                raise TypeError("Output data type must be a string or bytes")
