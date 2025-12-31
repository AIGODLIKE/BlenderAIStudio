import requests
from typing import Self
from enum import Enum
from threading import Thread
from bpy.app.translations import pgettext as _T
from .exception import (
    APIRequestException,
    AuthFailedException,
    InsufficientBalanceException,
    ToeknExpiredException,
)

SERVICE_URL = "http://dc0.mc-cx.com:63333"


class Account:
    _INSTANCE = None

    def __new__(cls, *args, **kwargs):
        if cls._INSTANCE is None:
            cls._INSTANCE = super().__new__(cls)
        return cls._INSTANCE

    def __init__(self) -> None:
        self.auth_mode = AuthMode.ACCOUNT
        self.acount_name = "Not Login"
        self.logged_in = False
        self.credits = 0
        self.api_key = "fake api key"
        self.token = ""
        self.price_table = {}
        self.initialized = False
        self.error_messages: list = []

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

    def refresh_login_status(self):
        pass

    def login(self):
        self.logged_in = True

    def logout(self):
        self.logged_in = False
        self.acount_name = "Not Login"
        self.credits = 0

    # 兑换积分
    def redeem_credits(self, code: str) -> int:
        url = f"{SERVICE_URL}/v1/billing/redeem-code"
        headers = {
            "token": self.token,
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
        resp.raise_for_status()
        if resp.status_code == 200:
            resp_json: dict = resp.json()
            data: dict = resp_json.get("data", {"amount": 0})
            code = resp_json.get("code")
            err_code = resp_json.get("errCode")
            err_msg = resp_json.get("errMsg", "")
            match code, err_code:
                case (-1, -1201):
                    self.push_error(InsufficientBalanceException("Invalid or insufficient balance!"))
                case (-1, -1202):
                    self.push_error(APIRequestException("API Request Error!"))
                case (-3, -3002):
                    pass
                case (-4, -4000):
                    self.push_error(AuthFailedException("Authentication failed!"))
                case (-4, -4001):
                    self.push_error(ToeknExpiredException("Token expired!"))
                case (-6, -6003):
                    pass
            if code != 0:
                print("兑换失败:", err_msg)
            else:
                amount = data.get("amount", 0)
                self.credits += amount
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
            self.push_error(_T("Price fetch failed") + ": "  + resp.text)

    def fetch_credits(self):
        if self.price_table:
            return
        url = f"{SERVICE_URL}/billing/balance"
        headers = {
            "token": self.token,
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
            self.push_error(_T("Credits fetch failed") + ": "  + resp.text)

def init_account():
    account = Account.get_instance()
    Thread(target=account.init, daemon=True).start()
    return 1


class AuthMode(Enum):
    ACCOUNT = "Account Mode (Recommended)"
    API = "API Key Mode"


def register():
    import bpy

    bpy.app.timers.register(init_account, first_interval=1, persistent=True)


def unregister():
    import bpy

    bpy.app.timers.unregister(init_account)


if __name__ == "__main__":
    account = Account()
    account.auth_mode = AuthMode.ACCOUNT
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
