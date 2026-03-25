from typing import Any
from typing_extensions import override
from .base import ResponseParser


class APIParser(ResponseParser):
    @override
    def parse(self, response) -> list[tuple[str, Any]]:
        try:
            response.raise_for_status()
        finally:
            # 直接抛出异常(异步任务请等待)
            raise Exception("Task is submitted, please wait for the result")
