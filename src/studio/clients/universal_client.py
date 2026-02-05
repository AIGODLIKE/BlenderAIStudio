import bpy
import time
from traceback import print_exc
from bpy.app.translations import pgettext_iface as _T
from pathlib import Path
from typing import Iterable, Dict, Any, List

from .base import StudioClient, StudioHistoryItem
from ..utils import save_mime_typed_datas_to_temp_files, load_images_into_blender
from ..account import Account
from ..config.model_registry import ModelConfig, ModelRegistry
from ..tasks import UniversalModelTask, Task, TaskResult
from ...preferences import AuthMode
from ...logger import logger
from ...utils import get_pref


class UniversalClient(StudioClient):
    """通用客户端 - 基于配置驱动的多模型支持

    **核心特性：**
    - 支持任意 AI 模型（图像、音频、视频、文本）
    - 通过 models_config.json 配置模型
    - 动态生成 UI 参数（无需硬编码）
    - 支持多认证模式（API Key / Account）
    - 每个模型独立保存参数值

    **职责：**
    - 参数存储和访问 (get_value/set_value)
    - 模型配置管理 (ModelConfig)
    - 价格计算 (calc_price)
    - 任务提交入口 (add_task)
    """

    # 默认使用的模型 ID
    DEFAULT_MODEL_ID = "gemini-3-pro-image-preview"
    DEFAULT_MODEL_NAME = "NanoBananaPro"

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.help_url = ""
        # 为每个模型保存独立的参数值
        self._model_params: Dict[str, Dict[str, Any]] = {}

        self._model_config: ModelConfig = None

        self._meta_cache: Dict[str, Dict[str, Any]] = {}

        # 额外参数(不会传递给模型,用于UI显示)
        self._extra_params: List[Dict[str, Any]] = []
        # 1. 批量渲染 任务数(整数, [1, 8])
        self._extra_params.append(
            {
                "name": "batch_count",
                "display_name": "Batch Count",
                "type": "INT",
                "hide_title": True,
                "default": 1,
                "min": 1,
                "max": 8,
                "step": 1,
            }
        )

        # 当前选择的模型 ID
        self._current_model_name = self.DEFAULT_MODEL_NAME

        # 动态加载模型配置
        self._model_registry = ModelRegistry.get_instance()
        self._update_model_config()

        # 生成 meta（用于 UI）
        self._meta_cache[self.model_name] = self._generate_meta()

        self._last_fetch_task_timestamp = 0
        self._fetch_task_interval = 10

    @property
    def api_key(self) -> str:
        # TODO 特殊变量
        # 先尝试从模型参数获取
        # api_key_from_params = self.get_value("api_key")
        # if api_key_from_params:
        #     return api_key_from_params
        api_key = get_pref().get_api_key_by_model_name(self.model_name)
        if api_key:
            return str(api_key).strip()
        return ""

    @api_key.setter
    def api_key(self, value: str) -> None:
        # TODO 特殊变量
        # 保存到模型参数
        # self.set_value("api_key", value)
        get_pref().set_api_key_by_model_name(self.model_name, value)
        bpy.context.preferences.use_preferences_save = True

    @property
    def model_config(self):
        """获取当前模型配置"""
        return self._model_config

    @property
    def model_name(self) -> str:
        return self._model_config.model_name if self._model_config else ""

    @property
    def model_id(self) -> str:
        account = Account.get_instance()
        if account.auth_mode == AuthMode.API.value:
            return self._model_config.model_id
        strategy = account.pricing_strategy
        return self._model_registry.resolve_submit_id(self.model_name, strategy)

    @property
    def meta(self) -> Dict[str, Any]:
        return self._meta_cache.get(self.model_name, {})

    @property
    def current_model_name(self) -> str:
        """当前选择的模型 ID"""
        return self._current_model_name

    @current_model_name.setter
    def current_model_name(self, model_name: str):
        """切换模型"""
        if model_name != self._current_model_name:
            self._current_model_name = model_name
            self._update_model_config()

    @property
    def batch_count(self) -> int:
        return self.get_value("batch_count") or 1

    def get_value(self, prop: str):
        if prop == "api_key":
            return self.api_key
        model_params = self._get_model_params()
        return model_params.get(prop, None)

    def set_value(self, prop: str, value):
        if prop == "api_key":
            self.api_key = value
            return
        self._get_model_params()[prop] = value

    def _get_model_params(self) -> Dict[str, Any]:
        self._ensure_default_params(self._current_model_name)
        return self._model_params[self._current_model_name]

    def _ensure_default_params(self, model_name: str):
        self._model_params.setdefault(model_name, self._default_params())

    def _default_params(self):
        params = {}
        if not self._model_config:
            return params
        for pdef in self._model_config.parameters + self._extra_params:
            pname = pdef.get("name")
            if not pname:
                continue
            params[pname] = pdef.get("default", self._get_default(pdef))
        return params

    def _get_default(self, param_def: dict):
        param_type = param_def.get("type", "STRING")
        if param_type == "STRING":
            return ""
        elif param_type == "ENUM":
            options = param_def.get("options", [])
            return options[0] if options else ""
        elif param_type == "NUMBER":
            return 0
        elif param_type == "BOOLEAN":
            return False
        elif param_type == "IMAGE_LIST":
            return []
        return None

    def _update_model_config(self):
        """更新当前模型配置"""
        try:
            self._model_config = self._model_registry.get_model(self._current_model_name)

            pref = get_pref()
            account = Account.get_instance()
            auth_mode = account.auth_mode if pref.is_backup_mode else AuthMode.API.value
            self.help_url = self._model_config.get_help_url(auth_mode)

            # 重新生成 meta(缓存模型参数)
            if self.model_name not in self._meta_cache:
                self._meta_cache[self.model_name] = self._generate_meta()
        except ValueError as e:
            logger.error(f"无法加载模型配置: {e}")
            self._model_config = None

    def _generate_meta(self) -> Dict[str, Any]:
        """从 ModelConfig 动态生成 meta 配置

        完全从 ModelConfig.parameters 中加载，不再硬编码任何参数。
        """
        meta = {}

        params = []
        if not self._model_config:
            logger.warning("模型配置未加载")
        elif not self._model_config.parameters:
            logger.warning(f"模型 {self._current_model_name} 没有参数定义")
        else:
            params = self._model_config.parameters

        # 从 ModelConfig 加载所有参数
        for param in params + self._extra_params:
            param_name = param.get("name")
            if not param_name:
                continue

            # 复制参数定义
            meta[param_name] = {
                "display_name": param.get("display_name", param_name),
                "category": param.get("category", "Input"),
                "type": param.get("type", "STRING"),
                "hide_title": param.get("hide_title", False),
            }

            # 可选字段
            if "multiline" in param:
                meta[param_name]["multiline"] = param["multiline"]
            if "default" in param:
                meta[param_name]["default"] = param["default"]
            if "options" in param:
                meta[param_name]["options"] = param["options"]
            if "limit" in param:
                meta[param_name]["limit"] = param["limit"]
            if "min" in param:
                meta[param_name]["min"] = param["min"]
            if "max" in param:
                meta[param_name]["max"] = param["max"]
            if "step" in param:
                meta[param_name]["step"] = param["step"]

            # ✅ 新增：visible_when 和 processor 字段
            if "visible_when" in param:
                meta[param_name]["visible_when"] = param["visible_when"]
            if "processor" in param:
                meta[param_name]["processor"] = param["processor"]

        return meta

    def supports_auth_mode(self, auth_mode: str) -> bool:
        """检查当前模型是否支持指定的认证模式"""
        if not self._model_config:
            return True  # 配置加载失败时允许所有模式
        return self._model_config.supports_auth_mode(auth_mode)

    def get_supported_auth_modes(self) -> list[str]:
        """获取当前模型支持的认证模式列表（返回配置文件中的小写值）"""
        if not self._model_config:
            return [AuthMode.API.value, AuthMode.ACCOUNT.value]
        return self._model_config.auth_modes

    def get_properties(self) -> Iterable[str]:
        return self.meta.keys()

    def get_meta(self, prop: str):
        return self.meta.get(prop, {})

    def on_image_action(self, prop: str, action: str, index: int = -1) -> None:
        """
        TODO 该方法不应该在这里实现
        """
        if action == "upload_image":
            upload_image(self, prop)
        elif action == "replace_image":
            replace_image(self, prop, index)
        elif action == "delete_image":
            delete_image(self, prop, index)

    def calc_price(self) -> int | None:
        """计算价格，Account 模式使用动态价格，API 模式使用静态配置"""
        resolution = self.get_value("resolution") or "1K"
        strategy = Account.get_instance().pricing_strategy
        price = self._model_registry.calc_price(self.model_name, strategy, resolution)
        return price * self.batch_count

    def _should_fetch_task_status(self) -> bool:
        return time.time() - self._last_fetch_task_timestamp > self._fetch_task_interval

    def fetch_task_status(self):
        if not self._should_fetch_task_status():
            return
        task_ids = []
        for item in self.history.find_all_needs_status_sync_items():
            task_ids.append(item.task_id)
        if not task_ids:
            return
        Account.get_instance().add_task_ids_to_fetch_status_threaded(task_ids)
        self._last_fetch_task_timestamp = time.time()

    def add_task(self, account: "Account"):
        # 预校验
        if not self._validate_before_submit(account):
            return

        # 构建原始参数（不包含 image_path，由 Task 渲染）
        params = self._build_raw_params()

        # 获取凭证
        model_id = self.model_id
        if account.auth_mode == AuthMode.API.value:
            credentials = {"api_key": self.api_key}
        else:
            resolution = self.get_value("resolution") or "1K"
            credentials = {
                "token": account.token,
                "modelId": model_id,
                "size": resolution,
            }
        for _ in range(self.batch_count):
            self._add_task_one(account, credentials, params)

    def _add_task_one(self, account: "Account", credentials, params):
        task = UniversalModelTask(
            model_id=self.model_id,
            auth_mode=account.auth_mode,
            credentials=credentials,
            params=params,
            context=bpy.context.copy(),
        )
        self._register_task_callbacks(task)
        task.register_callback("completed", self._on_completed)
        # 提交任务
        self.task_id = self.task_manager.submit_task(task)
        item = StudioHistoryItem()
        item.task_id = self.task_id
        item.model = self.model_name
        item.created_at = time.time()
        item.started_at = time.time()
        item.status = StudioHistoryItem.STATUS_PREPARING
        item.metadata.setdefault("params", {}).update(params)
        self.history.add(item)
        logger.info(f"任务已提交: {self.task_id}")

    def _on_completed(self, event_data):
        task: Task = event_data["task"]
        result: TaskResult = event_data["result"]
        parsed_data: list[tuple[str, str | bytes]] = result.data
        metadata: Dict[str, Any] = result.metadata
        try:
            outputs = self._save_result_file(parsed_data)
            self._update_history_item_on_complete(task.task_id, parsed_data, outputs, metadata)
            self._load_into_blender(outputs)
        except Exception:
            logger.exception("处理任务结果时发生错误")
            print_exc()

        Account.get_instance().fetch_credits()

    @staticmethod
    def _save_result_file(parsed_data: list[tuple[str, str | bytes]]) -> list[str]:
        """保存结果文件

        Args:
            parsed_data: 处理后的响应数据，每个元素为 (mime_type, data) 元组

        Returns:
            保存的文件路径列表
        """
        return save_mime_typed_datas_to_temp_files(parsed_data)

    @staticmethod
    def _load_into_blender(outputs: list[tuple[str, str]]):
        load_images_into_blender(outputs)

    def _update_history_item_on_complete(
        self,
        task_id: str,
        response_data: list,
        outputs: list[tuple[str, str]],
        metadata: Dict[str, Any],
    ):
        item = self.history.find_by_task_id(task_id)
        if not item:
            return
        item.result = response_data
        item.outputs = outputs
        item.metadata.update(metadata)
        item.model = metadata.get("model_name", item.model)
        item.timestamp = time.time()
        item.status = StudioHistoryItem.STATUS_SUCCESS
        item.finished_at = time.time()
        self.history.update_item(item)
        logger.info(f"任务完成: {task_id}")

    def cancel_generate_task(self):
        self.task_manager.cancel_task(self.task_id)
        self.task_id = ""
        # TODO 从历史中移除

    def _build_raw_params(self) -> Dict[str, Any]:
        params = {}

        for param_name in self.meta.keys():
            if param_name in ["api_key"]:
                continue
            value = self.get_value(param_name)
            if value is not None:
                params[param_name] = value

        params["__use_internal_prompt"] = self.use_internal_prompt

        return params

    def _validate_before_submit(self, account: "Account") -> bool:
        """提交前验证"""
        pref = get_pref()

        # 检查缓存目录
        if not Path(pref.output_cache_dir).exists():
            self.push_error(_T("Cache folder not find, please change..."))
            return False

        # 检查模型配置
        if not self._model_config:
            self.push_error(_T("Model configuration not loaded"))
            return False

        # 检查认证模式支持
        if not self._model_config.supports_auth_mode(account.auth_mode):
            self.push_error(_T(f"Model {self._current_model_name} does not support {account.auth_mode} mode"))
            return False

        # 根据认证模式检查凭证
        if account.auth_mode == AuthMode.API.value:
            if not self.api_key:
                self.push_error(_T("API Key not set"))
                return False
        else:  # account 模式
            if not account.logged_in:
                self.push_error(_T("Please login first"))
                return False
            if not account.token:
                self.push_error(_T("Account token not found"))
                return False

        return True


def upload_image(client: StudioClient, prop: str):
    def upload_image_callback(files_path: list[str]):
        # TODO 参考图片数量有限制,需要处理
        l = client.get_value(prop)
        for file_path in files_path:
            if file_path not in l:
                l.append(file_path)
        client.get_value(prop)[:] = client.get_value(prop)[:10]

    from ..ops import FileCallbackRegistry

    callback_id = FileCallbackRegistry.register_callback(upload_image_callback)
    bpy.ops.bas.file_importer("INVOKE_DEFAULT", callback_id=callback_id)


def replace_image(client: StudioClient, prop: str, index: int = -1):
    def replace_image_callback(files_path: list[str]):
        if len(files_path) >= 1:
            file_path = files_path[0]
            try:
                client.get_value(prop)[index] = file_path
            except IndexError:
                client.get_value(prop).append(file_path)

    from ..ops import FileCallbackRegistry

    callback_id = FileCallbackRegistry.register_callback(replace_image_callback)
    bpy.ops.bas.file_importer("INVOKE_DEFAULT", callback_id=callback_id)


def delete_image(client: StudioClient, prop: str, index: int):
    client.get_value(prop).pop(index)
