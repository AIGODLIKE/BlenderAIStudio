import requests
from typing import Self
from enum import Enum
from threading import Thread

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
    def redeem_credits(self, code: str):
        url = f"{SERVICE_URL}/v1/billing/redeem-code"
        headers = {
            "token": "",
            "Content-Type": "application/json",
        }
        payload = {
            "code": code,
        }
        resp = requests.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        if resp.status_code == 200:
            resp_json = resp.json()
            data: dict = resp_json.get("data", {"amount": 0})
            code = resp_json.get("code")
            err_msg = resp_json.get("errMsg")
            if code != 0:
                print("兑换失败:", err_msg)
            else:
                amount = data.get("amount", 0)
                self.credits += amount
                print("兑换成功:", amount)
        else:
            print("兑换失败:", resp.status_code, resp.text)

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
            self.push_error("网络连接失败")
            return
        if resp.status_code == 404:
            self.push_error("价格列表获取失败")
            return
        resp.raise_for_status()
        if resp.status_code == 200:
            resp_json: dict = resp.json()
            code = resp_json.get("code")
            err_msg = resp_json.get("errMsg")
            if code != 0:
                self.push_error("获取价格失败:" + err_msg)
                return
            data: dict = resp_json.get("data", {})
            self.price_table = data
        else:
            self.push_error("获取价格失败:" + resp.text)


def init_account():
    account = Account.get_instance()
    Thread(target=account.init, daemon=True).start()
    return 1


class AuthMode(Enum):
    ACCOUNT = "账号模式(推荐)"
    API = "API模式"


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
