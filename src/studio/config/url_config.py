import logging

try:
    from ...logger import logger
except ImportError:
    logger = logging.getLogger("[URLConfigManager]")


class URLConfigManager:
    """URL 配置管理器（单例）

    职责：
    - 统一管理所有服务 URL
    - 支持正式/测试环境切换
    - 从 preferences 读取配置
    - 提供 URL 构建方法

    """

    # 正式环境固定配置
    PRODUCTION_CONFIG = {
        "help_url": "https://shimo.im/docs/47kgMZ7nj4Sm963V",
        "api_base_url": "https://api-addon.acggit.com",
        "api_version": "v1",
        "login_url": "https://addon-login.acggit.com",
    }

    _instance = None

    def __init__(self):
        """初始化 URL 配置管理器"""
        pass

    @classmethod
    def get_instance(cls):
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def is_dev_environment(self) -> bool:
        """检查是否使用测试环境

        Returns:
            True 如果使用测试环境，False 使用正式环境
        """
        try:
            from ...utils import get_pref

            return get_pref().use_dev_environment
        except Exception as e:
            logger.warning(f"Failed to get environment setting: {e}, using production")
            return False

    def get_help_url(self) -> str:
        return self.PRODUCTION_CONFIG["help_url"]

    def get_service_base_url(self) -> str:
        if self.is_dev_environment():
            try:
                from ...utils import get_pref

                url = get_pref().dev_api_base_url.strip().rstrip("/")
                if url:
                    return url
            except Exception as e:
                logger.warning(f"Failed to get dev_api_base_url: {e}, using production")
        return self.PRODUCTION_CONFIG["api_base_url"]

    def get_service_url(self) -> str:
        base = self.get_service_base_url()
        version = self.PRODUCTION_CONFIG["api_version"]
        return f"{base}/{version}"

    def get_login_url(self) -> str:
        if self.is_dev_environment():
            try:
                from ...utils import get_pref

                url = get_pref().dev_login_url.strip()
                if url:
                    return url
            except Exception as e:
                logger.warning(f"Failed to get dev_login_url: {e}, using production")
        return self.PRODUCTION_CONFIG["login_url"]

    def get_dev_token(self) -> str:
        if self.is_dev_environment():
            try:
                from ...utils import get_pref

                token = get_pref().dev_token.strip()
                return token if token else ""
            except Exception as e:
                logger.warning(f"Failed to get dev_token: {e}")
        return ""

    def get_model_api_base_url(self, auth_mode: str) -> str | None:
        if auth_mode == "account":
            # account 模式使用服务 URL
            return self.get_service_url()
        # api 模式返回 None，使用模型自己的配置
        return None
