from enum import Enum


class State:
    _INSTANCE = None

    def __new__(cls, *args, **kwargs):
        if cls._INSTANCE is None:
            cls._INSTANCE = super().__new__(cls)
        return cls._INSTANCE

    def __init__(self) -> None:
        self.auth_mode = AuthMode.ACCOUNT
        self.acount_name = "Not Login"
        self.credits = 0
        self.api_key = "fake api key"

    @classmethod
    def get_instance(cls) -> "State":
        if cls._INSTANCE is None:
            cls._INSTANCE = cls()
        return cls._INSTANCE


class AuthMode(Enum):
    ACCOUNT = "账号模式(推荐)"
    API = "API模式"
