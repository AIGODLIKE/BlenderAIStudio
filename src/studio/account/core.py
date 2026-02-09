import json
import tempfile
import traceback
import webbrowser
from copy import deepcopy
from pathlib import Path
from threading import Thread
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from typing import Self

import requests
from bpy.app.translations import pgettext as _T

from .network import get_session
from .task_history import AccountTaskHistory, TaskHistoryData
from .task_sync import TaskSyncService, TaskStatusPoller
from .websocket import WebSocketClient
from ..config.model_registry import ModelRegistry
from ..config.url_config import URLConfigManager
from ..exception import (
    APIRequestException,
    AuthFailedException,
    ParameterValidationException,
    InsufficientBalanceException,
    RedeemCodeException,
    InternalException,
    DatabaseUpdateException,
    ToeknExpiredException,
)
from ...logger import logger
from ...preferences import AuthMode
from ...utils import get_pref


# 认证文件路径
AUTH_PATH = Path(tempfile.gettempdir(), "aistudio/auth.json")
try:
    AUTH_PATH.parent.mkdir(parents=True, exist_ok=True)
except Exception as e:
    print("mkdir file error", e.args)


class Account:
    """账户管理类（单例）

    职责：
    - 用户认证（登录、登出）
    - 积分管理（查询、兑换）
    - 价格表管理
    - 任务状态查询（网络层）
    - 错误队列管理
    """

    _INSTANCE = None
    _AUTH_PATH = AUTH_PATH

    def __new__(cls, *args, **kwargs):
        if cls._INSTANCE is None:
            cls._INSTANCE = super().__new__(cls)
        return cls._INSTANCE

    def __init__(self) -> None:
        # 避免重复初始化
        if hasattr(self, "_initialized") and self._initialized:
            return

        # 用户信息
        self.nickname = ""
        self.logged_in = False
        self.services_connected = False
        self.credits = 0
        self._token = ""  # 内部 token 存储

        # 价格表
        self.price_table = []
        self.provider_count_map = {}

        # 任务历史和同步服务
        self.task_history = AccountTaskHistory()
        self.sync_service = TaskSyncService(self, self.task_history)
        self.task_poller = TaskStatusPoller(self, self.sync_service, interval=15)

        # 兑换积分表
        self.redeem_to_credits_table = {
            6: 600,
            30: 3300,
            60: 7200,
            100: 13000,
        }

        # 状态标志
        self.initialized = False
        self.error_messages: list = []
        self.waiting_for_login = False

        # URL 管理器
        self._url_manager = URLConfigManager.get_instance()

        # 加载本地账户信息
        self.load_account_info_from_local()

        # 检测服务连接状态
        self.ping_once()

        self._initialized = True

    # ==================== 属性 ====================

    @property
    def auth_mode(self) -> str:
        return get_pref().account_auth_mode

    @auth_mode.setter
    def auth_mode(self, mode: str):
        get_pref().set_account_auth_mode(mode)

    @property
    def pricing_strategy(self) -> str:
        return get_pref().account_pricing_strategy

    @pricing_strategy.setter
    def pricing_strategy(self, strategy: str):
        get_pref().set_account_pricing_strategy(strategy)

    def provider_count(self, model_name: str) -> int:
        for price_data in self.price_table:
            if price_data.get("modelName") == model_name:
                return price_data.get("providerCount", 0)
        return 0

    @property
    def help_url(self) -> str:
        return self._url_manager.get_help_url()

    @property
    def service_url(self) -> str:
        return self._url_manager.get_service_url()

    @property
    def login_url(self) -> str:
        return self._url_manager.get_login_url()

    @property
    def token(self) -> str:
        # 如果使用测试环境且设置了测试 token，优先使用
        dev_token = self._url_manager.get_dev_token()
        if dev_token:
            return dev_token
        return self._token

    @token.setter
    def token(self, value: str):
        self._token = value

    # ==================== 单例和初始化 ====================

    @classmethod
    def get_instance(cls) -> "Self":
        if cls._INSTANCE is None:
            cls._INSTANCE = cls()
        return cls._INSTANCE

    def init(self):
        if self.initialized:
            return
        logger.debug("初始化账户")
        self.initialized = True
        self.fetch_credits_price()

    # ==================== 错误管理 ====================

    def take_errors(self) -> list:
        errors = self.error_messages[:]
        self.error_messages.clear()
        return errors

    def push_error(self, error):
        self.error_messages.append(error)

    # ==================== 登录状态 ====================

    def is_logged_in(self) -> bool:
        return self.logged_in

    def is_waiting_for_login(self) -> bool:
        return self.waiting_for_login

    def refresh_login_status(self):
        pass  # 预留方法

    # ==================== 登录/登出 ====================

    def login(self):
        if self.waiting_for_login:
            return

        self.waiting_for_login = True
        webbrowser.open(self.login_url)

        async def login_callback(server: WebSocketClient, websocket, event: dict):
            try:
                data: dict = event.get("data", {})
                self.load_account_info(data)
                self.save_account_info(data)
                response = {
                    "type": "send_token_return",
                    "data": {
                        "status": "ok",
                        "host": "Blender",
                    },
                }
                await websocket.send(json.dumps(response))
                server.stop_event.set()
            except Exception:
                pass

        def run(port_range):
            server = None
            for p in range(*port_range):
                try:
                    server = WebSocketClient(p)
                    server.reg_handler("send_token", login_callback)
                    server.run()
                    break
                except OSError:
                    logger.debug(f"Port {p} is in use")
                except Exception:
                    traceback.print_exc()

            if not server:
                logger.critical("No available port found")
            self.waiting_for_login = False

        job = Thread(target=run, args=((55441, 55451),), daemon=True)
        job.start()

    def logout(self):
        self.logged_in = False
        self.nickname = "Not Login"
        self.credits = 0
        self._token = ""
        if not self._AUTH_PATH.exists():
            return
        try:
            self._AUTH_PATH.unlink()
        except Exception:
            pass

    # ==================== 账户信息加载/保存 ====================

    def load_account_info_from_local(self):
        if not self._AUTH_PATH.exists():
            return
        try:
            data = json.loads(self._AUTH_PATH.read_text())
            self.load_account_info(data)
            self.fetch_credits()
        except Exception:
            traceback.print_exc()
            self.push_error(_T("Can't load auth file"))

    def load_account_info(self, data: dict):
        if not isinstance(data, dict):
            print(data)
            self.push_error(_T("Invalid auth data"))
            return
        self.nickname = data.get("nickname", "")
        self._token = data.get("token", "")
        self.credits = data.get("coin", 0)
        self.logged_in = True

    def save_account_info(self, data: dict):
        if not self._AUTH_PATH.parent.exists():
            try:
                self._AUTH_PATH.parent.mkdir(parents=True)
            except Exception:
                traceback.print_exc()
                self.push_error(_T("Can't create auth directory"))
        try:
            self._AUTH_PATH.write_text(json.dumps(data, ensure_ascii=True, indent=2))
        except Exception:
            traceback.print_exc()
            self.push_error(_T("Can't save auth file"))

    # ==================== 服务连接检测 ====================

    def ping_once(self):
        url = f"{self.service_url}/billing/model-price"
        headers = {
            "Content-Type": "application/json",
        }

        def job():
            try:
                session = get_session()
                resp = session.get(url, headers=headers, timeout=2)
                self.services_connected = resp.status_code == 200
            except Exception:
                self.services_connected = False

        Thread(target=job, daemon=True).start()

    # ==================== 积分管理 ====================

    def redeem_credits(self, code: str) -> int:
        url = f"{self.service_url}/billing/redeem-code"
        headers = {
            "X-Auth-T": self.token,
            "Content-Type": "application/json",
        }
        payload = {
            "code": code,
        }
        try:
            session = get_session()
            resp = session.request(method="POST", url=url, headers=headers, json=payload)
        except ConnectionError:
            self.push_error(_T("Network connection failed"))
            return 0
        except Exception:
            traceback.print_exc()
            self.push_error(_T("Network connection failed"))
            return 0
        if resp.status_code == 404:
            self.push_error(_T("Redeem failed"))
            return 0
        if resp.status_code == 502:
            self.push_error(_T("Server Error: Bad Gateway"))
            return 0

        resp.raise_for_status()

        if resp.status_code == 200:
            resp_json: dict = resp.json()
            data: dict = resp_json.get("data", {"amount": 0})
            code = resp_json.get("code")
            err_msg = resp_json.get("errMsg", "")

            if err_msg:
                err_type_map = {
                    "参数校验错误": ParameterValidationException("Parameter validation failed!"),
                    "兑换码错误": RedeemCodeException("Redeem code error!"),
                    "数据库更新错误（不需要展示）": DatabaseUpdateException("Database update error!"),
                    "内部错误（不需要展示）": InternalException("Internal error!"),
                    "余额不足": InsufficientBalanceException("Insufficient balance!"),
                    "API请求错误!": APIRequestException("API Request Error!"),
                    "鉴权错误": AuthFailedException("Authentication failed!"),
                    "Token过期": ToeknExpiredException("Token expired!"),
                }
                err = err_type_map.get(err_msg, Exception(err_msg))
                self.push_error(err)

            if code != 0:
                print("兑换失败:", err_msg)
            else:
                amount = data.get("amount", 0)
                self.credits = amount
                print("兑换成功:", amount)
                return amount
        else:
            print("兑换失败:", resp.status_code, resp.text)
        return 0

    def fetch_credits(self):
        def _fetch_credits():
            if self.auth_mode != AuthMode.ACCOUNT.value:
                return
            url = f"{self.service_url}/billing/balance"
            headers = {
                "X-Auth-T": self.token,
                "Content-Type": "application/json",
            }
            try:
                session = get_session()
                resp = session.get(url, headers=headers)
            except ConnectionError:
                self.push_error(_T("Network connection failed"))
                return
            except Exception:
                traceback.print_exc()
                self.push_error(_T("Network connection failed"))
                return

            if resp.status_code == 404:
                self.push_error(_T("Credits fetch failed"))
                return
            if resp.status_code == 502:
                self.push_error(_T("Server Error: Bad Gateway"))
                return

            resp.raise_for_status()

            if resp.status_code == 200:
                resp_json: dict = resp.json()
                code = resp_json.get("code")
                err_code = resp_json.get("errCode")
                err_msg = resp_json.get("errMsg", "")

                match code, err_code:
                    case (-4, -4000):
                        self.push_error(AuthFailedException("Authentication failed!"))
                    case (-4, -4001):
                        self.push_error(ToeknExpiredException("Token expired!"))

                if code != 0:
                    self.push_error(_T("Credits fetch failed") + ": " + err_msg)
                    return
                self.credits = resp_json.get("data", 0)
            else:
                self.push_error(_T("Credits fetch failed") + ": " + resp.text)

        Thread(target=_fetch_credits, daemon=True).start()

    # ==================== 价格表管理 ====================

    def fetch_credits_price(self):
        def _fetch_credits_price():
            if self.price_table:
                return
            url = f"{self.service_url}/billing/model-price"
            headers = {
                "Content-Type": "application/json",
            }
            try:
                session = get_session()
                resp = session.get(url, headers=headers)
            except ConnectionError:
                self.push_error(_T("Network connection failed"))
                return
            except Exception:
                traceback.print_exc()
                self.push_error(_T("Network connection failed"))
                return

            if resp.status_code == 404:
                self.push_error(_T("Price fetch failed"))
                return
            if resp.status_code == 502:
                self.push_error(_T("Server Error: Bad Gateway"))
                return

            resp.raise_for_status()

            if resp.status_code == 200:
                resp_json: dict = resp.json()
                code = resp_json.get("code")
                err_msg = resp_json.get("errMsg")

                if code != 0:
                    self.push_error(_T("Price fetch failed") + ": " + err_msg)
                    return

                data: dict = resp_json.get("data", {})
                self.price_table = deepcopy(data)
                pricing_data = {}

                for item in data:
                    model_name = item.pop("modelName", None)
                    self.provider_count_map[model_name] = item.pop("providerCount", 0)
                    pricing_data[model_name] = deepcopy(item)

                ModelRegistry.get_instance().update_pricing_from_backend(pricing_data)

                id_map = {}
                for model_name, model_data in pricing_data.items():
                    for value in model_data.values():
                        if isinstance(value, dict) and "modelId" in value:
                            id_map[value["modelId"]] = model_name

                ModelRegistry.get_instance().update_id_to_name(AuthMode.ACCOUNT.value, id_map)
            else:
                self.push_error(_T("Price fetch failed") + ": " + resp.text)

        Thread(target=_fetch_credits_price, daemon=True).start()

    # ==================== 任务状态查询 ====================

    def add_task_ids_to_fetch_status_threaded(self, task_ids: list[str]):
        self.task_poller.add_pending_task_ids(task_ids)

    def add_task_ids_to_fetch_status_now(self, task_ids: list[str]):
        def _job(task_ids: list[str]):
            self.sync_service.sync_tasks(task_ids)

        Thread(target=_job, args=(task_ids,), daemon=True).start()

    def _fetch_task_status(self, task_ids: list[str]) -> dict:
        url = f"{self.service_url}/service/history"

        headers = {
            "X-Auth-T": self.token,
            "Content-Type": "application/json",
        }

        payload = {
            "reqIds": task_ids,
        }

        try:
            session = get_session()
            resp = session.get(url, headers=headers, json=payload, timeout=10)
            resp.raise_for_status()
            resp_json = resp.json()
            return resp_json
        except requests.RequestException as e:
            logger.error(f"Failed to fetch task status: {e}")
            raise

    def fetch_task_history(self, task_ids: list[str]) -> dict[str, TaskHistoryData]:
        return self.task_history.fetch_task_history(task_ids)
