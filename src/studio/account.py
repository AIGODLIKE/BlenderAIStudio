import asyncio
import json
import requests
import tempfile
import traceback
import webbrowser
from copy import deepcopy
from pathlib import Path
from threading import Thread
from typing import Self
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

import bpy
from bpy.app.translations import pgettext as _T

from .config.model_registry import ModelRegistry
from .config.url_config import URLConfigManager
from .exception import (
    APIRequestException,
    AuthFailedException,
    ParameterValidationException,
    InsufficientBalanceException,
    RedeemCodeException,
    InternalException,
    DatabaseUpdateException,
    ToeknExpiredException,
)
from ..logger import logger
from ..preferences import AuthMode
from ..utils import get_pref

try:
    from ...External.websockets.server import serve
    from ...External.websockets.exceptions import ConnectionClosedOK, ConnectionClosed
except Exception:
    from websockets.server import serve
    from websockets import WebSocketServerProtocol
    from websockets.exceptions import ConnectionClosedOK, ConnectionClosed

AUTH_PATH = Path(tempfile.gettempdir(), "aistudio/auth.json")
try:
    AUTH_PATH.parent.mkdir(parents=True, exist_ok=True)
except Exception as e:
    print("mkdir file error", e.args)

# 重试策略
RETRY_TOTAL = 5
RETRY_STATUS_FORCELIST = [429, 500, 502, 503, 504]
RETRY_ALLOWED_METHODS = ["HEAD", "GET", "PUT", "DELETE", "OPTIONS", "TRACE"]
RETRY_BACKOFF_FACTOR = 0.5

RETRY_STRATEGY = Retry(
    total=RETRY_TOTAL,
    status_forcelist=RETRY_STATUS_FORCELIST,
    allowed_methods=RETRY_ALLOWED_METHODS,
    backoff_factor=RETRY_BACKOFF_FACTOR,
)

# 适配器
ADAPTER = HTTPAdapter(max_retries=RETRY_STRATEGY)


def get_session() -> requests.Session:
    session = requests.Session()
    session.mount("https://", ADAPTER)
    session.mount("http://", ADAPTER)
    return session


class Account:
    _INSTANCE = None
    _AUTH_PATH = AUTH_PATH

    def __new__(cls, *args, **kwargs):
        if cls._INSTANCE is None:
            cls._INSTANCE = super().__new__(cls)
        return cls._INSTANCE

    def __init__(self) -> None:
        self.nickname = ""
        self.logged_in = False
        self.services_connected = False
        self.credits = 0
        self._token = ""  # 内部 token 存储
        self.price_table = {}
        self.provider_count_map = {}
        self.redeem_to_credits_table = {
            6: 600,
            30: 3300,
            60: 7200,
            100: 13000,
        }
        self.initialized = False
        self.error_messages: list = []
        self.waiting_for_login = False
        self._url_manager = URLConfigManager.get_instance()
        self.load_account_info_from_local()
        self.ping_once()

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

    @property
    def help_url(self) -> str:
        return self._url_manager.get_help_url()

    @property
    def service_url(self) -> str:
        """获取服务 URL（动态，支持环境切换）"""
        return self._url_manager.get_service_url()

    @property
    def login_url(self) -> str:
        """获取登录 URL（动态，支持环境切换）"""
        return self._url_manager.get_login_url()

    @property
    def token(self) -> str:
        """获取 token（支持测试环境 token）"""
        # 如果使用测试环境且设置了测试 token，优先使用
        dev_token = self._url_manager.get_dev_token()
        if dev_token:
            return dev_token
        return self._token

    @token.setter
    def token(self, value: str):
        """设置 token"""
        self._token = value

    def take_errors(self) -> list:
        errors = self.error_messages[:]
        self.error_messages.clear()
        return errors

    def push_error(self, error):
        self.error_messages.append(error)

    def init(self):
        if self.initialized:
            return
        logger.debug("初始化账户")
        self.initialized = True
        self.fetch_credits_price()

    @classmethod
    def get_instance(cls) -> Self:
        if cls._INSTANCE is None:
            cls._INSTANCE = cls()
        return cls._INSTANCE

    def is_logged_in(self) -> bool:
        return self.logged_in

    def is_waiting_for_login(self) -> bool:
        return self.waiting_for_login

    def refresh_login_status(self):
        pass

    def login(self):
        if self.waiting_for_login:
            return
        self.waiting_for_login = True
        webbrowser.open(self.login_url)

        async def login_callback(server: WebSocketClient, websocket: "WebSocketServerProtocol", event: dict):
            try:
                data: dict = event.get("data", {})
                self.load_account_info(data)
                self.save_account_info(data)
                event = {
                    "type": "send_token_return",
                    "data": {
                        "status": "ok",
                        "host": "Blender",
                    },
                }
                await websocket.send(json.dumps(event))
                server.stop_event.set()
            except ConnectionClosedOK:
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
        """{
            "id": 0,
            "email": "test@on.ink",
            "nickname": "TEST",
            "avatar": "xxx",
            "coin": 1564,
            "token": "xxx",
        }"""
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

    # 兑换积分
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
            err_code = resp_json.get("errCode")
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


class WebSocketClient:
    _host = "127.0.0.1"

    def __init__(self, port):
        self.host = self._host
        self.port = port
        self.logger = logger
        self._handlers = {}
        self.stop_event = asyncio.Event()

        self.reg_handler("_default", self._default)
        self.reg_handler("query_status", self._query_status)

    def reg_handler(self, etype, handler):
        self._handlers[etype] = handler

    def unreg_handler(self, etype):
        del self._handlers[etype]

    async def call_handler(self, websocket: "WebSocketServerProtocol", message):
        try:
            event: dict = json.loads(message)
        except json.JSONDecodeError:
            return
        if not isinstance(event, dict):
            event = {}
        etype = event.get("type", "_default")
        handler = self._handlers.get(etype, self._default)
        try:
            await handler(self, websocket, event)
        except Exception as e:
            self.logger.error(f"Error in handler {handler.__name__}: {e}")
            self.logger.error(traceback.format_exc())

    @staticmethod
    async def _default(server: "WebSocketClient", websocket: "WebSocketServerProtocol", event: dict):
        try:
            server.logger.warning(f"默认消息: {event}")
            event = {
                "type": "default",
                "data": event,
            }
            await websocket.send(json.dumps(event))
        except ConnectionClosedOK:
            pass

    @staticmethod
    async def _query_status(server: "WebSocketClient", websocket: "WebSocketServerProtocol", event: dict):
        try:
            server.logger.warning(f"查询状态: {event}")
            event = {
                "type": "query_status_return",
                "data": {
                    "status": "ok",
                    "host": "Blender",
                },
            }
            await websocket.send(json.dumps(event))
        except ConnectionClosedOK:
            pass

    async def handle(self, websocket: "WebSocketServerProtocol", path: str):
        try:
            self.logger.debug(f"Client Connected: {websocket}")
            async for message in websocket:
                await self.call_handler(websocket, message)
        except ConnectionClosed as e:
            self.logger.debug(f"客户端断开: {e.code} (code={e.code}, reason='{e.reason}')")
        except Exception as e:
            self.logger.critical(f"客户端异常: {e}")

    async def main(self):
        async with serve(self.handle, self.host, self.port, max_size=None):
            self.logger.warning(f"Server running on port {self.port}")
            await self.stop_event.wait()  # 阻塞直到设置 stop

    def run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self.main())


def init_account():
    def init():
        account = Account.get_instance()
        account.init()

    Thread(target=init, daemon=True).start()
    return 1


def register():
    bpy.app.timers.register(init_account, first_interval=1, persistent=True)


def unregister():
    if bpy.app.timers.is_registered(init_account):
        bpy.app.timers.unregister(init_account)
