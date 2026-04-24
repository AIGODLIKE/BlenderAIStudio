import base64
import logging
import mimetypes
import requests

from typing import List, Tuple, Any, Optional
from .base import ResponseParser
from .utils import _check_response_account_mode
from ...core.exception import StudioException

try:
    from ....logger import logger
except Exception:
    logger = logging.getLogger(__name__)


class GPTImageParser(ResponseParser):
    """GPT Image (gpt-image-1) 响应解析器

    Account 模式下响应被包装在 {"data": {...}} 中。
    """

    def __init__(self, is_account_mode: bool = False):
        self.is_account_mode = is_account_mode

    def parse(self, response: requests.Response) -> List[Tuple[str, Any]]:
        self._check_response(response)
        resp_json = response.json()
        self._check_response_custom(resp_json)
        data = self._process_resp_json(resp_json)

        try:
            res = _parse_image_data_from_response_json(data)
        except Exception as e:
            print(data)
            raise e
        return res

    def _check_response_custom(self, resp: dict):
        print(resp)
        _check_response_account_mode(resp)

    def _process_resp_json(self, resp) -> dict:
        if self.is_account_mode:
            resp = resp.get("data", {}) if isinstance(resp, dict) else {}
            if not resp:
                raise GPTImageAPIError("Invalid response format")
        return resp

    def _check_response(self, response: requests.Response) -> None:
        code = response.status_code
        if code == 200:
            return
        if code in (401, 403):
            raise GPTImageAPIError("Authentication failed or token expired.")
        if code == 429:
            raise GPTImageAPIError("Rate limit exceeded.")
        if code == 400:
            logger.debug(getattr(response, "text", ""))
            raise GPTImageAPIError("Bad request (400), please check the network and proxy")
        if code == 502:
            logger.debug(getattr(response, "text", ""))
            raise GPTImageAPIError("Server Error: Bad Gateway.")
        try:
            j = response.json()
            if isinstance(j, dict) and "error" in j:
                err = j.get("error")
                if isinstance(err, dict):
                    msg = err.get("message") or str(err)
                    raise GPTImageAPIError(msg)
                raise GPTImageAPIError(str(err))
            raise GPTImageAPIError(str(j))
        except Exception:
            logger.error(response.text)
            raise GPTImageAPIError("API request failed. Unknown error.")


class GPTImageAPIError(StudioException):
    pass


def _parse_image_data_from_response_json(resp: dict) -> List[Tuple[str, bytes]]:
    if not isinstance(resp, dict):
        raise GPTImageAPIError("Invalid response format")

    # OpenAI 格式: {"data": [{"b64_json": "..."}], ...}
    data_list = resp.get("data")
    if isinstance(data_list, list) and data_list:
        item = data_list[0] if isinstance(data_list[0], dict) else None
        if not item:
            raise GPTImageAPIError("Invalid response format - data item is not an object")

        if isinstance(item.get("b64_json"), str):
            b64 = item.get("b64_json")
        else:
            raise GPTImageAPIError("Generating... please wait...")
    else:
        b64 = resp.get("b64_json")

    if result := _parse_b64_data(b64):
        return result

    if "error" in resp:
        err = resp.get("error")
        if isinstance(err, dict):
            raise GPTImageAPIError(err.get("message") or str(err))
        raise GPTImageAPIError(str(err))

    raise GPTImageAPIError("Invalid response format - missing image data.")


def _parse_b64_data(b64: str) -> Optional[List[Tuple[str, bytes]]]:
    if isinstance(b64, str) and b64:
        b64_data = b64.split("base64,", maxsplit=1)[1] if "base64," in b64 else b64
        mime = mimetypes.guess_type(b64) or ("image/png", None)
        img_bytes = base64.b64decode(b64_data)
        return [(mime[0], img_bytes)]
