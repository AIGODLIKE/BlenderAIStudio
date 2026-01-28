import requests

from typing import List, Tuple, Any
from .base import ResponseParser


class SeedreamImageParser(ResponseParser):
    def __init__(self, is_account_mode: bool = False):
        self.is_account_mode = is_account_mode

    def parse(self, response: requests.Response) -> List[Tuple[str, Any]]:
        return []
