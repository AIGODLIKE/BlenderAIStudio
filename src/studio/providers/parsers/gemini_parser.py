import base64
import logging
import numpy as np
import OpenImageIO as oiio
import requests
import tempfile

from pathlib import Path
from typing import List, Tuple, Any
from .base import ResponseParser
from ...exception import (
    StudioException,
    InsufficientBalanceException,
    APIRequestException,
    AuthFailedException,
    ToeknExpiredException,
)
from ....utils import get_temp_folder

try:
    from ....logger import logger
except Exception:
    logger = logging.getLogger(__name__)


class GeminiImageParser(ResponseParser):
    """Gemini 图像响应解析器

    处理 Gemini API 的响应，包括：
    - 自定义错误检查（Gemini 特有的错误格式）
    - 图像数据解析

    支持两种模式：
    - API 模式：直接返回 Gemini 原始响应
    - 账号模式：响应被包装在 {"data": {...}} 中
    """

    def __init__(self, is_account_mode: bool = False):
        self.is_account_mode = is_account_mode

    def parse(self, response) -> List[Tuple[str, Any]]:
        """解析 Gemini API 响应

        支持两种模式：
        - API 模式：直接从 response.json() 解析
        - 账号模式：从 response.json()["data"] 解析

        Args:
            response: requests.Response 对象

        Returns:
            List[Tuple[str, Any]]: 解析后的图像数据

        Raises:
            各种 GeminiAPIError: 解析失败时抛出对应异常
        """
        # 检查 HTTP 状态码
        self._check_response(response)

        # 获取 JSON 响应
        resp_json = response.json()

        # 检查响应体中的错误
        self._check_response_custom(resp_json)

        # 账号模式：提取 data 字段
        data = self._process_resp_json(resp_json)

        # 复用现有触析逻辑
        return _parse_image_data_from_response_json(data)

    def _check_response_custom(self, resp: dict):
        """
        TODO 限制到账号模式
        """
        # {'responseId': 2005309135796568064, 'code': -4, 'errCode': -4000, 'errMsg': '请先登录!'}
        err_msg = resp.get("errMsg", "")
        code = resp.get("code")
        err_code = resp.get("errCode")
        if not err_msg:
            return
        print("_check_response_custom", resp)
        err_type_map = {
            "余额不足": InsufficientBalanceException("Insufficient balance!"),
            "API请求错误!": APIRequestException("API Request Error!"),
            "鉴权错误": AuthFailedException("Authentication failed!"),
            "Token过期": ToeknExpiredException("Token expired!"),
        }
        raise err_type_map.get(err_msg, Exception(err_msg))

    def _process_resp_json(self, resp) -> dict:
        if self.is_account_mode:
            resp = resp.get("data", {}) if isinstance(resp, dict) else {}
            if not resp:
                raise GeminiAPIError("Invalid response format")
        return resp

    def _check_response(self, response: requests.Response) -> None:
        resp = response
        code = resp.status_code
        if code == 403:
            raise GeminiAPIError("API key invalid or quota exceeded,Please Check your Google AI Studio account")
        elif code == 429:
            raise GeminiAPIError("Rate limit exceeded,Please check your API key and Google AI Studio account")
        elif code == 400:
            logger.debug(resp.text)
            raise GeminiAPIError("Bad request (400),Please check the network and proxy")
        elif code == 502:
            logger.debug(resp.text)
            raise GeminiAPIError("Server Error: Bad Gateway,Please check the network and proxy.")
        elif code != 200:
            try:
                error_info: dict = resp.json().get("error", {})
                _code = error_info.get("code")
                if "message" in error_info:
                    error_message = error_info.get("message", "Unknown error")
                    raise GeminiAPIError(error_message)
                raise Exception
            except Exception:
                logger.error(resp.text)
                raise GeminiAPIError("API request failed. Unknown error.")


class GeminiAPIError(StudioException):
    pass


class GeminiAPISafetyError(StudioException):
    pass


class GeminiAPIOtherError(StudioException):
    pass


class GeminiAPIBlockListError(StudioException):
    pass


class GeminiAPIProhibitedContentError(StudioException):
    pass


class GeminiAPIImageSafetyError(StudioException):
    pass


def _parse_image_data_from_response_json(resp: dict) -> List[Tuple[str, bytes]]:
    # block case
    block_reason = resp.get("promptFeedback", {}).get("blockReason")
    match block_reason:
        case "PROHIBITED_CONTENT":
            raise GeminiAPIProhibitedContentError("NanoBanana Blocked by PROHIBITED_CONTENT")
        case "SAFETY":
            raise GeminiAPISafetyError("NanoBanana Blocked by SAFETY")
        case "OTHER":
            raise GeminiAPIOtherError("NanoBanana Blocked by OTHER")
        case "BLOCKLIST":
            raise GeminiAPIBlockListError("NanoBanana Blocked by BLOCKLIST")
        case "IMAGE_SAFETY":
            raise GeminiAPIImageSafetyError("NanoBanana Blocked by IMAGE_SAFETY")

    if "candidates" not in resp or not resp["candidates"]:
        logger.debug(str(resp))
        raise GeminiAPIError("No image generated. The model may have rejected the request.")

    candidate = resp["candidates"][0]

    if "content" not in candidate:
        raise GeminiAPIError("Invalid response format - no content in candidate")

    parts: list[dict] = candidate["content"]["parts"]

    # 查找图片数据
    for part in parts:
        inline_data_key = None
        if "inline_data" in part:
            inline_data_key = "inline_data"
        elif "inlineData" in part:
            inline_data_key = "inlineData"

        if not inline_data_key:
            continue
        inline_data: dict = part[inline_data_key]

        data_key = None
        if "data" in inline_data:
            data_key = "data"
        elif "bytes" in inline_data:
            data_key = "bytes"

        if not data_key:
            continue

        if not inline_data[data_key]:
            continue
        mime_type = inline_data.get("mime_type", inline_data.get("mimeType", "image/jpeg"))
        image_data = base64.b64decode(inline_data[data_key])
        return [(mime_type, image_data)]

    # 无图时，返回占位符图片
    text_parts = [part.get("text", "") for part in parts]
    if any(text_parts):
        return _create_placeholder_image()
    raise GeminiAPIError("No image data found in API response")


def _create_placeholder_image() -> List[Tuple[str, bytes]]:
    try:
        width, height = 100, 100
        png_data = _create_empty_image(width, height, (0, 100, 200))
        return [("image/png", png_data)]
    except Exception as e:
        raise GeminiAPIError(f"Failed to create placeholder: {str(e)}")


def _create_empty_image(width: int, height: int, color: tuple) -> bytes:
    temp_folder = get_temp_folder(prefix="gen")
    with tempfile.NamedTemporaryFile(suffix=".png", dir=temp_folder) as f:
        spec = oiio.ImageSpec(width, height, len(color), oiio.UINT8)
        out = oiio.ImageOutput.create(f.name)
        if not out:
            raise Exception(f"Could not create ImageOutput for {f.name}")
        pixels = np.full((height, width, len(color)), color, dtype=np.uint8)
        out.open(f.name, spec)
        out.write_image(pixels)
        out.close()
        png_data = Path(f.name).read_bytes()
        return png_data
