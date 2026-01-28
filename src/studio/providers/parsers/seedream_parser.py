import base64
import logging
import mimetypes
import requests

from typing import List, Tuple, Any, Optional
from .base import ResponseParser
from ...exception import (
    StudioException,
    InsufficientBalanceException,
    APIRequestException,
    AuthFailedException,
    ToeknExpiredException,
)

try:
    from ....logger import logger
except Exception:
    logger = logging.getLogger(__name__)


class SeedreamImageParser(ResponseParser):
    def __init__(self, is_account_mode: bool = False):
        self.is_account_mode = is_account_mode

    def parse(self, response: requests.Response) -> List[Tuple[str, Any]]:
        # 检查 HTTP 状态码
        self._check_response(response)

        # 获取 JSON 响应
        resp_json = response.json()

        # 检查响应体中的错误
        self._check_response_custom(resp_json)

        # 账号模式：提取 data 字段
        data = self._process_resp_json(resp_json)

        try:
            res = _parse_image_data_from_response_json(data)
        except Exception as e:
            print(data)
            raise e
        return res

    def _check_response_custom(self, resp: dict):
        # 账号端点常见：{'responseId': ..., 'code': -4, 'errCode': -4000, 'errMsg': '请先登录!'}
        if not isinstance(resp, dict):
            return
        err_msg = resp.get("errMsg", "")
        if not err_msg:
            return
        err_type_map = {
            "余额不足": InsufficientBalanceException("Insufficient balance!"),
            "API请求错误!": APIRequestException("API Request Error!"),
            "鉴权错误": AuthFailedException("Authentication failed!"),
            "Token过期": ToeknExpiredException("Token expired!"),
        }
        raise err_type_map.get(err_msg, SeedreamAPIError(err_msg))

    def _process_resp_json(self, resp) -> dict:
        if self.is_account_mode:
            resp = resp.get("data", {}) if isinstance(resp, dict) else {}
            if not resp:
                raise SeedreamAPIError("Invalid response format")
        return resp

    def _check_response(self, response: requests.Response) -> None:
        code = response.status_code
        if code == 200:
            return
        if code in (401, 403):
            raise SeedreamAPIError("Authentication failed or token expired.")
        if code == 429:
            raise SeedreamAPIError("Rate limit exceeded.")
        if code == 400:
            logger.debug(getattr(response, "text", ""))
            raise SeedreamAPIError("Bad request (400),Please check the network and proxy")
        if code == 502:
            logger.debug(getattr(response, "text", ""))
            raise SeedreamAPIError("Server Error: Bad Gateway.")
        try:
            j = response.json()
            # OpenAI 风格 error
            if isinstance(j, dict) and "error" in j:
                err = j.get("error")
                if isinstance(err, dict):
                    msg = err.get("message") or str(err)
                    raise SeedreamAPIError(msg)
                raise SeedreamAPIError(str(err))
            raise SeedreamAPIError(str(j))
        except Exception:
            logger.error(response.text)
            raise SeedreamAPIError("API request failed. Unknown error.")


class SeedreamAPIError(StudioException):
    pass


def _parse_image_data_from_response_json(resp: dict) -> List[Tuple[str, bytes]]:
    if not isinstance(resp, dict):
        raise SeedreamAPIError("Invalid response format")

    # data示例：{"data":[{"b64_json": "...", "size": "1760x2368"}], ...}
    data_list = resp.get("data")
    if isinstance(data_list, list) and data_list:
        item = data_list[0] if isinstance(data_list[0], dict) else None
        if not item:
            raise SeedreamAPIError("Invalid response format - data item is not an object")

        if isinstance(item.get("b64_json"), str):
            b64 = item.get("b64_json")
        else:
            raise SeedreamAPIError("No image data found in response.")
    else:
        # 兼容：直接返回 {"b64_json": "..."}
        b64 = resp.get("b64_json")

    if result := _parse_b64_data(b64):
        return result

    # OpenAI 风格 error
    if "error" in resp:
        err = resp.get("error")
        if isinstance(err, dict):
            raise SeedreamAPIError(err.get("message") or str(err))
        raise SeedreamAPIError(str(err))

    raise SeedreamAPIError("Invalid response format - missing image data.")


def _parse_b64_data(b64: str) -> Optional[Tuple[str, bytes]]:
    if isinstance(b64, str) and b64:
        b64_data = b64.split("base64,", maxsplit=1)[1] if "base64," in b64 else b64
        mime = mimetypes.guess_type(b64) or ("image/jpeg", None)
        img_bytes = base64.b64decode(b64_data)
        return [(mime[0], img_bytes)]
