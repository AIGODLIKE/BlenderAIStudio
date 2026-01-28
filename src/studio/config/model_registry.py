import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from ...logger import logger
except ImportError:
    logger = logging.getLogger("[ModelRegistry]")


class SimpleYAMLParser:
    """简单的 YAML 解析器

    精简支持：
    - 基本的 key: value
    - 列表（- item）
    - 嵌套结构
    - 字符串、数字、布尔值、null
    - 注释（# 开头）
    - 引号字符串
    """

    def __init__(self):
        self.lines = []
        self.current_line = 0

    def parse(self, text: str) -> Any:
        """解析 YAML 文本

        Args:
            text: YAML 格式的文本

        Returns:
            解析后的 Python 对象（字典/列表）
        """
        self.lines = text.split("\n")
        self.current_line = 0
        result, _ = self._parse_block(0)
        return result

    def _get_indent(self, line: str) -> int:
        """获取行的缩进级别"""
        return len(line) - len(line.lstrip())

    def _is_empty_or_comment(self, line: str) -> bool:
        """判断是否为空行或注释"""
        stripped = line.strip()
        return not stripped or stripped.startswith("#")

    def _parse_value(self, value: str) -> Any:
        """解析值的类型

        支持：字符串、数字、布尔值、null、空列表、空对象、行内列表、行内字典
        """
        value = value.strip()

        # 空值
        if not value:
            return ""

        # 行内列表 [item1, item2, ...]
        if value.startswith("[") and value.endswith("]"):
            return self._parse_inline_list(value)

        # 行内字典 {key1: value1, key2: value2, ...}
        if value.startswith("{") and value.endswith("}"):
            return self._parse_inline_dict(value)

        # null
        if value.lower() == "null":
            return None

        # 布尔值
        if value.lower() == "true":
            return True
        if value.lower() == "false":
            return False

        # 引号字符串
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            return value[1:-1]

        # 数字
        try:
            if "." in value:
                return float(value)
            return int(value)
        except ValueError:
            pass

        # 普通字符串
        return value

    def _parse_inline_list(self, value: str) -> list:
        """解析行内列表 [item1, item2, ...]"""
        # 去掉首尾的方括号
        content = value[1:-1].strip()

        # 空列表
        if not content:
            return []

        # 分割列表项（简单实现，不处理嵌套）
        items = []
        current_item = ""
        in_quotes = False
        quote_char = None

        for char in content:
            if char in ('"', "'") and (not in_quotes or char == quote_char):
                in_quotes = not in_quotes
                quote_char = char if in_quotes else None
                current_item += char
            elif char == "," and not in_quotes:
                items.append(self._parse_value(current_item.strip()))
                current_item = ""
            else:
                current_item += char

        # 添加最后一项
        if current_item.strip():
            items.append(self._parse_value(current_item.strip()))

        return items

    def _parse_inline_dict(self, value: str) -> dict:
        """解析行内字典 {key1: value1, key2: value2, ...}"""
        # 去掉首尾的花括号
        content = value[1:-1].strip()

        # 空字典
        if not content:
            return {}

        # 分割键值对（简单实现，不处理嵌套）
        result = {}
        current_pair = ""
        in_quotes = False
        quote_char = None

        for char in content:
            if char in ('"', "'") and (not in_quotes or char == quote_char):
                in_quotes = not in_quotes
                quote_char = char if in_quotes else None
                current_pair += char
            elif char == "," and not in_quotes:
                # 解析当前键值对
                if ":" in current_pair:
                    key_val = current_pair.split(":", 1)
                    key = key_val[0].strip()
                    val = key_val[1].strip()
                    result[key] = self._parse_value(val)
                current_pair = ""
            else:
                current_pair += char

        # 添加最后一对
        if current_pair.strip() and ":" in current_pair:
            key_val = current_pair.split(":", 1)
            key = key_val[0].strip()
            val = key_val[1].strip()
            result[key] = self._parse_value(val)

        return result

    def _parse_block(self, base_indent: int) -> tuple:
        """解析一个块（对象或列表）

        Args:
            base_indent: 基础缩进级别

        Returns:
            (解析结果, 消耗的行数)
        """
        result = None
        is_list = False
        list_items = []
        dict_items = {}
        consumed_lines = 0

        while self.current_line < len(self.lines):
            line = self.lines[self.current_line]

            # 跳过空行和注释
            if self._is_empty_or_comment(line):
                self.current_line += 1
                consumed_lines += 1
                continue

            indent = self._get_indent(line)
            stripped = line.strip()

            # 缩进减少，返回上层
            if indent < base_indent:
                break

            # 缩进过大，跳过（由上层递归处理）
            if indent > base_indent:
                break

            # 列表项
            if stripped.startswith("- "):
                is_list = True
                item_content = stripped[2:].strip()

                if ":" in item_content and not item_content.startswith('"'):
                    # 列表项是对象：- key: value
                    self.current_line += 1
                    consumed_lines += 1

                    # 先解析当前行的 key: value
                    item_obj = {}
                    key, val = item_content.split(":", 1)
                    key = key.strip()
                    val = val.strip()

                    if val:
                        item_obj[key] = self._parse_value(val)
                    else:
                        # 值为空，可能有嵌套
                        nested, nested_consumed = self._parse_block(indent + 2)
                        item_obj[key] = nested
                        consumed_lines += nested_consumed

                    # 检查是否有同级的其他字段
                    while self.current_line < len(self.lines):
                        next_line = self.lines[self.current_line]
                        if self._is_empty_or_comment(next_line):
                            self.current_line += 1
                            consumed_lines += 1
                            continue

                        next_indent = self._get_indent(next_line)
                        next_stripped = next_line.strip()

                        if next_indent == indent + 2 and ":" in next_stripped and not next_stripped.startswith("- "):
                            # 同级字段
                            key, val = next_stripped.split(":", 1)
                            key = key.strip()
                            val = val.strip()

                            if val:
                                item_obj[key] = self._parse_value(val)
                            else:
                                self.current_line += 1
                                consumed_lines += 1
                                nested, nested_consumed = self._parse_block(indent + 4)
                                item_obj[key] = nested
                                consumed_lines += nested_consumed
                                continue

                            self.current_line += 1
                            consumed_lines += 1
                        else:
                            break

                    list_items.append(item_obj)
                else:
                    # 列表项是简单值
                    if not item_content:
                        # 空值后面可能有嵌套
                        self.current_line += 1
                        consumed_lines += 1
                        nested, nested_consumed = self._parse_block(indent + 2)
                        list_items.append(nested)
                        consumed_lines += nested_consumed
                    else:
                        list_items.append(self._parse_value(item_content))
                        self.current_line += 1
                        consumed_lines += 1

            # 键值对
            elif ":" in stripped:
                key_val = stripped.split(":", 1)
                key = key_val[0].strip()
                value = key_val[1].strip() if len(key_val) > 1 else ""

                if value:
                    # 有值
                    dict_items[key] = self._parse_value(value)
                    self.current_line += 1
                    consumed_lines += 1
                else:
                    # 无值，检查下一行
                    self.current_line += 1
                    consumed_lines += 1

                    if self.current_line < len(self.lines):
                        next_line = self.lines[self.current_line]

                        # 跳过空行和注释
                        while self.current_line < len(self.lines) and self._is_empty_or_comment(self.lines[self.current_line]):
                            self.current_line += 1
                            consumed_lines += 1

                        if self.current_line < len(self.lines):
                            next_line = self.lines[self.current_line]
                            next_indent = self._get_indent(next_line)

                            if next_indent > indent:
                                # 有嵌套内容
                                nested, nested_consumed = self._parse_block(next_indent)
                                dict_items[key] = nested
                                consumed_lines += nested_consumed
                            else:
                                # 无嵌套，值为空字符串
                                dict_items[key] = ""
                        else:
                            dict_items[key] = ""
            else:
                # 无法识别的行，跳过
                self.current_line += 1
                consumed_lines += 1

        # 返回结果
        if is_list:
            result = list_items
        elif dict_items:
            result = dict_items
        else:
            result = {}

        return result, consumed_lines

    @classmethod
    def load(cls, filepath: str) -> Any:
        """从文件加载 YAML

        Args:
            filepath: YAML 文件路径

        Returns:
            解析后的 Python 对象
        """
        with open(filepath, "r", encoding="utf-8") as f:
            text = f.read()

        parser = cls()
        return parser.parse(text)


class ModelConfig:
    """模型配置类

    从配置文件加载并管理单个模型的所有配置信息。
    """

    def __init__(self, config_dict: dict):
        self.model_id: str = config_dict["modelId"]
        self.model_name: str = config_dict["modelName"]
        self.provider: str = config_dict["provider"]
        self.category: str = config_dict["category"]
        self.auth_modes: List[str] = config_dict["auth_modes"]
        self.endpoints: Dict[str, Dict[str, Any]] = config_dict["endpoints"]
        self.parameters: Optional[List[Dict[str, Any]]] = config_dict.get("parameters")
        self.request_builder: Optional[str] = config_dict.get("request_builder")
        self.response_parser: Optional[str] = config_dict.get("response_parser")

        self.actions: Dict[str, Dict[str, str]] = config_dict.get("actions", {})
        self.default_action: str = config_dict.get("default_action", "generate")

        self.input_processors: List[Dict[str, Any]] = config_dict.get("input_processors") or []

    def get_endpoint(self, auth_mode: str) -> Dict[str, Any]:
        """获取对应认证模式的端点配置

        Args:
            auth_mode: 认证模式

        Returns:
            端点配置字典，包含 base_url, entry, method, headers 等
        """
        endpoint = self.endpoints.get(auth_mode)
        if not endpoint:
            raise ValueError(f"Auth mode '{auth_mode}' not supported for model '{self.model_id}'")
        return endpoint

    def get_help_url(self, auth_mode: str) -> str:
        """获取帮助文档 URL"""
        endpoint = self.get_endpoint(auth_mode)
        return endpoint.get("help_url", "")

    def build_api_url(self, auth_mode: str) -> str:
        """构建完整的 API URL（支持占位符替换）

        Args:
            auth_mode: 认证模式

        Returns:
            完整的 API 端点 URL
        """
        endpoint = self.get_endpoint(auth_mode)
        base_url = endpoint.get("base_url", "")
        entry: str = endpoint.get("entry", "")

        # 如果 base_url 是占位符，从 URLConfigManager 获取
        if "{account_api_base_url}" in base_url:
            try:
                from .url_config import URLConfigManager
                url_manager = URLConfigManager.get_instance()
                dynamic_base_url = url_manager.get_model_api_base_url(auth_mode)
                if dynamic_base_url:
                    base_url = base_url.replace("{account_api_base_url}", dynamic_base_url)
            except Exception as e:
                logger.warning(f"Failed to resolve base_url placeholder: {e}")

        # 替换 entry 中的占位符
        entry = entry.replace("{model}", self.model_id)

        return f"{base_url}/{entry}" if entry else base_url

    def get_parameter(self, param_name: str) -> Optional[Dict[str, Any]]:
        """根据参数名获取参数定义

        Args:
            param_name: 参数名称

        Returns:
            参数定义字典，如果不存在返回 None
        """
        for param in self.parameters or []:
            if param.get("name") == param_name:
                return param
        return None

    def supports_auth_mode(self, auth_mode: str) -> bool:
        """检查是否支持指定的认证模式"""
        return auth_mode in self.auth_modes

    def supports_action(self, action: str) -> bool:
        """检查是否支持指定的功能

        Args:
            action: 功能名称，如 "generate", "edit", "transfer"

        Returns:
            True 如果支持该功能
        """
        # 如果没有定义 actions，则支持所有功能（向后兼容）
        if not self.actions:
            return True
        return action in self.actions

    def get_action_info(self, action: str) -> Optional[Dict[str, str]]:
        """获取功能的详细信息

        Args:
            action: 功能名称

        Returns:
            功能信息字典，包含 display_name 和 description
        """
        return self.actions.get(action)

    def get_available_actions(self) -> List[str]:
        """获取所有支持的功能列表

        Returns:
            功能名称列表
        """
        if not self.actions:
            return [self.default_action]
        return list(self.actions.keys())

    def inherit_from_base(self, base_config: "ModelConfig"):
        """从基础模型继承配置

        特价模型可以继承基础模型的以下配置：
        - request_builder (请求构建器)
        - response_parser (响应解析器)
        - parameters (参数定义)
        - endpoints (API 端点，如果未定义)

        Args:
            base_config: 基础模型配置对象
        """
        # 继承请求构建器
        if not self.request_builder:
            self.request_builder = base_config.request_builder

        # 继承响应解析器
        if not self.response_parser:
            self.response_parser = base_config.response_parser

        # 继承输入处理器
        if not self.input_processors:
            self.input_processors = base_config.input_processors

        # 继承参数定义
        # 注意：只有当参数未定义（None）时才继承，空列表 [] 表示明确不需要参数
        if self.parameters is None:
            self.parameters = base_config.parameters

        # 继承端点配置（仅当特价模型未定义时）
        for auth_mode in base_config.auth_modes:
            if auth_mode not in self.endpoints and auth_mode in self.auth_modes:
                self.endpoints[auth_mode] = base_config.endpoints[auth_mode]

        # 继承 actions 和 default_action
        # 注意：只有当 actions 未定义或为空字典时才继承
        if not self.actions:
            self.actions = base_config.actions
            self.default_action = base_config.default_action


class ModelRegistry:
    """模型注册器（单例）

    负责加载和管理所有模型配置。
    支持 YAML 和 JSON 两种格式（优先使用 YAML）。
    提供模型查询、筛选等功能。
    """

    _instance = None

    def __init__(self):
        self.models: Dict[str, ModelConfig] = {}
        self._pricing_table: Dict[str, Dict[str, int]] = {}
        self._id_to_name_by_auth_mode: Dict[str, Dict[str, str]] = {}
        self._load_model_config()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _load_config_file(self) -> dict:
        """加载配置文件（支持 YAML 和 JSON）

        优先级：
        1. models_config.yaml
        2. models_config.json（备选）

        Returns:
            配置字典

        Raises:
            FileNotFoundError: 配置文件不存在
            ValueError: 配置格式错误
        """
        config_dir = Path(__file__).parent
        yaml_file = config_dir / "models_config.yaml"
        json_file = config_dir / "models_config.json"

        # 优先尝试加载 YAML
        if yaml_file.exists():
            try:
                logger.info("Loading config from YAML")
                data = SimpleYAMLParser.load(str(yaml_file))
                logger.info("Successfully loaded from YAML")
                return data
            except Exception as e:
                logger.error(f"Failed to load YAML ({e})")

        # 备选：加载 JSON
        if json_file.exists():
            try:
                logger.info("Loading config from JSON")
                with open(json_file, encoding="utf-8") as f:
                    data = json.load(f)
                logger.info("Successfully loaded from JSON")
                return data
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON in config file: {e}")

        return {}

    def _load_model_config(self):
        """从配置文件加载模型

        1. 加载配置文件
        2. 更新id到name映射(根据auth_mode分级)

        Raises:
            FileNotFoundError: 配置文件不存在
            ValueError: 配置格式错误
            KeyError: 必需字段缺失
        """
        try:
            data = self._load_config_file()
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            raise

        if "models" not in data:
            raise KeyError("Missing 'models' key in config file")

        for model_data in data["models"]:
            try:
                config = ModelConfig(model_data)
                self.models[config.model_name] = config
            except KeyError as e:
                logger.warning(f"Failed to parse base model: missing field {e}")
                continue

        # 加载id到name映射
        for model in self.models.values():
            for auth_mode in model.auth_modes:
                self._update_id_to_name_one(auth_mode, model.model_id, model.model_name)

        logger.info(f"Total models loaded: {len(self.models)}")

    def get_model(self, model_name: str) -> ModelConfig:
        """根据模型 Name 获取模型配置

        Args:
            model_name: 模型 Name

        Returns:
            ModelConfig 对象

        Raises:
            ValueError: 模型不存在
        """
        if model_name not in self.models:
            available = ", ".join(self.models.keys())
            raise ValueError(f"Model '{model_name}' not found. Available models: {available}")
        return self.models[model_name]

    def get_model_by_id(self, auth_mode: str, model_id: str) -> ModelConfig:
        model_name = self.resolve_model_name(auth_mode, model_id)
        if not model_name:
            error_msg = f"Model ID '{model_id}' not found."
            logger.error(error_msg)
            raise ValueError(error_msg)
        return self.get_model(model_name)

    def has_model(self, model_name: str) -> bool:
        """检查模型是否存在"""
        return model_name in self.models

    def get_all_models(self) -> List[ModelConfig]:
        """获取所有模型配置"""
        return list(self.models.values())

    def list_models(
        self,
        category: Optional[str] = None,
        auth_mode: Optional[str] = None,
        provider: Optional[str] = None,
    ) -> List[ModelConfig]:
        """列出符合条件的模型

        Args:
            category: 按类别筛选，如 "IMAGE_GENERATION"
            auth_mode: 按认证模式筛选
            provider: 按提供商筛选，如 "gemini"

        Returns:
            符合条件的模型配置列表
        """
        result = []
        for model in self.models.values():
            # 类别筛选
            if category and model.category != category:
                continue

            # 认证模式筛选
            if auth_mode and auth_mode not in model.auth_modes:
                continue

            # 提供商筛选
            if provider and model.provider != provider:
                continue

            result.append(model)
        return result

    def update_id_to_name(self, auth_mode: str, id_name_map: Dict[str, str]) -> None:
        """更新 ID 到 Name 的映射"""
        _id_name_map = self._id_to_name_by_auth_mode.setdefault(auth_mode, {})
        _id_name_map.update(id_name_map)

    def _update_id_to_name_one(self, auth_mode: str, model_id: str, model_name: str) -> None:
        """更新单个 ID 到 Name 的映射"""
        _id_name_map = self._id_to_name_by_auth_mode.setdefault(auth_mode, {})
        _id_name_map[model_id] = model_name

    def update_pricing_from_backend(self, pricing_table: Dict[str, Dict[str, int]]) -> None:
        """更新动态定价表"""
        self._pricing_table = pricing_table
        logger.info(f"Pricing data updated: {len(self._pricing_table)} models")

    def calc_price(self, model_name: str, pricing_strategy: str, resolution) -> int | None:
        price_entry: dict = self._pricing_table.get(model_name, {})
        price_info: dict = price_entry.get(pricing_strategy, {})
        all_prices: dict = price_info.get("price", {})
        price = all_prices.get(resolution, 9999999)
        return price

    def resolve_submit_id(self, model_name: str, strategy: Optional[str] = None) -> str:
        chosen_entry = self._pricing_table.get(model_name) or {}
        print_table = chosen_entry.get(strategy, {})
        submit_id = print_table.get("modelId")
        return submit_id

    def resolve_model_name(self, auth_mode: str, model_id: str) -> str:
        return self._id_to_name_by_auth_mode.get(auth_mode, {}).get(model_id, "")
