import asyncio
import json
import tempfile
import traceback
import webbrowser
import requests

from typing import Self
from pathlib import Path
from threading import Thread
from bpy.app.translations import pgettext as _T
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
from ..preferences import get_pref, AuthMode
from ..logger import logger

try:
    from ...External.websockets.server import serve
    from ...External.websockets.legacy.server import WebSocketServer
    from ...External.websockets.exceptions import ConnectionClosedOK, ConnectionClosed
except Exception:
    from websockets.server import serve
    from websockets import WebSocketServerProtocol
    from websockets.legacy.server import WebSocketServer
    from websockets.exceptions import ConnectionClosedOK, ConnectionClosed

HELP_URL = "https://shimo.im/docs/47kgMZ7nj4Sm963V"
SERVICE_BASE_URL = "https://api-addon.acggit.com"
SERVICE_URL = f"{SERVICE_BASE_URL}/v1"
LOGIN_URL = "https://addon-login.acggit.com"
AUTH_PATH = Path(tempfile.gettempdir(), "aistudio/auth.json")
try:
    AUTH_PATH.parent.mkdir(parents=True, exist_ok=True)
except Exception:
    pass


class Account:
    _INSTANCE = None
    _AUTH_PATH = AUTH_PATH

    def __new__(cls, *args, **kwargs):
        if cls._INSTANCE is None:
            cls._INSTANCE = super().__new__(cls)
        return cls._INSTANCE

    def __init__(self) -> None:
        self.nickname = ""
        self.help_url = HELP_URL
        self.logged_in = False
        self.services_connected = False
        self.credits = 0
        self.token = ""
        self.price_table = {}
        self.redeem_to_credits_table = {
            6: 600,
            30: 3300,
            60: 7200,
            100: 13000,
        }
        self.initialized = False
        self.error_messages: list = []
        self.waiting_for_login = False
        self.load_account_info_from_local()
        self.ping_once()

    @property
    def auth_mode(self) -> str:
        return get_pref().account_auth_mode

    @auth_mode.setter
    def auth_mode(self, mode: str):
        get_pref().set_account_auth_mode(mode)

    def take_errors(self) -> list:
        errors = self.error_messages[:]
        self.error_messages.clear()
        return errors

    def push_error(self, error):
        self.error_messages.append(error)

    def init(self):
        if self.initialized:
            return
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
        webbrowser.open(LOGIN_URL)

        async def login_callback(server: WebSocketServer, websocket: "WebSocketServerProtocol", event: dict):
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
                    server = WebSocketServer(p)
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
        url = f"{SERVICE_URL}/billing/model-price"
        headers = {
            "Content-Type": "application/json",
        }
        try:
            resp = requests.get(url, headers=headers)
            self.services_connected = resp.status_code == 200
        except Exception:
            self.services_connected = False

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
        {
            "id": 0,
            "email": "test@on.ink",
            "nickname": "TEST",
            "avatar": "xxx",
            "coin": 1564,
            "token": "xxx",
        }
        if not isinstance(data, dict):
            print(data)
            self.push_error(_T("Invalid auth data"))
            return
        self.nickname = data.get("nickname", "")
        self.token = data.get("token", "")
        self.credits = data.get("coin", 0)
        self.logged_in = True

    def save_account_info(self, data: dict):
        if not self._AUTH_PATH.parent.exists():
            self.push_error(_T("Can't create auth directory"))
            return
        try:
            self._AUTH_PATH.write_text(json.dumps(data))
        except Exception:
            traceback.print_exc()
            self.push_error(_T("Can't save auth file"))

    def logout(self):
        self.logged_in = False
        self.nickname = "Not Login"
        self.credits = 0
        self.token = ""
        if not self._AUTH_PATH.exists():
            return
        try:
            self._AUTH_PATH.unlink()
        except Exception:
            pass

    # 兑换积分
    def redeem_credits(self, code: str) -> int:
        url = f"{SERVICE_URL}/billing/redeem-code"
        headers = {
            "X-Auth-T": self.token,
            "Content-Type": "application/json",
        }
        payload = {
            "code": code,
        }
        try:
            resp = requests.post(url, headers=headers, json=payload)
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
        if self.price_table:
            return
        url = f"{SERVICE_URL}/billing/model-price"
        headers = {
            "Content-Type": "application/json",
        }
        try:
            resp = requests.get(url, headers=headers)
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
            self.price_table = data
        else:
            self.push_error(_T("Price fetch failed") + ": " + resp.text)

    def get_model_price_table(self, provider: str = "") -> dict:
        if not self.price_table:
            return {}
        # TODO 实现价格表获取
        return self.price_table[0]

    def calc_model_price(self, model: str = "") -> dict:
        if not self.price_table:
            return {}

        for item in self.price_table:
            if item.get("modelId") == model:
                return item
        return {}

    def fetch_credits(self):
        if self.auth_mode != AuthMode.ACCOUNT.value:
            return
        url = f"{SERVICE_URL}/billing/balance"
        headers = {
            "X-Auth-T": self.token,
            "Content-Type": "application/json",
        }
        try:
            resp = requests.get(url, headers=headers)
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


class WebSocketServer:
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
    async def _default(server: "WebSocketServer", websocket: "WebSocketServerProtocol", event: dict):
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
    async def _query_status(server: "WebSocketServer", websocket: "WebSocketServerProtocol", event: dict):
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
    account = Account.get_instance()
    Thread(target=account.init, daemon=True).start()
    return 1


def register():
    import bpy

    bpy.app.timers.register(init_account, first_interval=1, persistent=True)


def unregister():
    import bpy

    bpy.app.timers.unregister(init_account)


if __name__ == "__main__":
    account = Account()
    account.auth_mode = AuthMode.ACCOUNT.value
    account.account_name = "test"
    account.credits = 100
    account.fetch_credits_price()
    print(account.take_errors())
    print(account.auth_mode)
    print(account.account_name)
    print(account.credits)
    redeem_codes_test = [
        "BG030-43CD-8B9A-6B038795C00F",
        "BG064-4AF6-A608-590D571E3C56",
        "BG064-41B8-84E3-BF8D81833323",
        "BG030-46C2-86BF-935805F8CB2F",
        "BG064-44B3-84CF-E32E27170A9E",
        "BG100-4E82-96FC-E2B5C968A18B",
        "BG006-4EC3-80B3-ABDA0A592EB7",
        "BG006-430F-A7A8-67AF3F5093B9",
        "BG100-43A1-BAE7-658074646973",
        "BG030-4EB5-9756-0003E23FF052",
        "BG130-4EB5-9756-0003E23FF053",
    ]
    for code_test in redeem_codes_test:
        account.redeem_credits(code_test)
    print(account.take_errors())
    print(account.credits)
