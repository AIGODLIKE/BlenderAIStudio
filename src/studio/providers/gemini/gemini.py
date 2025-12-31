import base64
import OpenImageIO as oiio
import numpy as np
import requests
import json
import tempfile

from pathlib import Path
from typing import Tuple

from .config import Payload
from ..base import BaseProvider
from ...account import SERVICE_URL
from ....logger import logger
from ...exception import (
    StudioException,
    APIRequestException,
    AuthFailedException,
    InsufficientBalanceException,
    ToeknExpiredException,
)

###############################################################################
#         Reference: https://github.com/kovname/nano-banana-render            #
###############################################################################


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


class GeminiProvider(BaseProvider):
    def __init__(self, api_key: str, model="models/gemini-3-pro-image-preview"):
        self.api_key = api_key
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"
        self.model = model

    def build_api_url(self) -> str:
        return f"{self.base_url}/{self.model}:generateContent"

    def build_headers(self) -> dict:
        return {
            "x-goog-api-key": self.api_key,
            "Content-Type": "application/json",
            "X-Goog-Api-Client": "python-blender-addon",
        }

    def generate_image(self, payload: Payload) -> Tuple[bytes, str]:
        raise NotImplementedError

    def _process_resp_json(self, resp) -> dict:
        return resp


class GeminiImageGenerateProvider(GeminiProvider):
    def generate_image(self, payload: Payload) -> Tuple[bytes, str]:
        """
        由深度图和提示词生成图像(可选使用参考图作为 风格化/材质)
        Args:
            is_color_render: 为True即使用常规eevee渲染, False代表使用深度图(mist)
            width, height: 输出分辨率
        Returns: (image_data, format)
        """
        try:
            url = self.build_api_url()
            headers = self.build_headers()
            payload = payload.build_payload()
            response = requests.post(url, headers=headers, json=payload, timeout=300)
            self._check_response_status(response)
            resp = response.json()
            self._check_response_custom(resp)
            resp = self._process_resp_json(resp)
            return _parse_image_data_from_response_json(resp)
        except requests.RequestException as e:
            logger.debug(str(e))
            raise GeminiAPIError("Network error")
        except json.JSONDecodeError:
            raise GeminiAPIError("Failed to parse API response")
        except GeminiAPIError as e:
            raise e

    def _check_response_status(self, resp: requests.Response):
        code = resp.status_code
        if code == 403:
            raise GeminiAPIError("API key invalid or quota exceeded. Check your Google AI Studio account.")
        elif code == 429:
            raise GeminiAPIError("Rate limit exceeded.")
        elif code == 400:
            logger.debug(resp.text)
            raise GeminiAPIError("Bad request (400).")
        elif code == 502:
            logger.debug(resp.text)
            raise GeminiAPIError("Server Error: Bad Gateway")
        elif code != 200:
            logger.debug(resp.text)
            raise GeminiAPIError("API request failed. Unknown error.")

    def _check_response_custom(self, resp: dict):
        pass


class GeminiImageEditProvider(GeminiImageGenerateProvider):
    pass


class AccountGeminiImageProvider(GeminiImageGenerateProvider):
    def __init__(self, api_key: str, model: str = ""):
        super().__init__(api_key, model)
        self.base_url = SERVICE_URL
        self.model = "gemini-3-pro-image-preview"
        self.entry = "service/cpick"

    def build_api_url(self) -> str:
        return f"{self.base_url}/{self.entry}"

    def build_headers(self) -> dict:
        return {
            "X-Auth-T": self.api_key,
            "Content-Type": "application/json",
        }

    def _process_resp_json(self, resp) -> dict:
        resp = resp.get("data", {})
        if not resp:
            raise GeminiAPIError("Invalid response format")
        return resp

    def _check_response_custom(self, resp: dict):
        # {'responseId': 2005309135796568064, 'code': -4, 'errCode': -4000, 'errMsg': '请先登录!'}
        err_msg = resp.get("errMsg", "")
        code = resp.get("code")
        err_code = resp.get("errCode")
        if not err_msg:
            return
        err_type_map = {
            "余额不足": InsufficientBalanceException("Insufficient balance!"),
            "API请求错误!": APIRequestException("API Request Error!"),
            "鉴权错误": AuthFailedException("Authentication failed!"),
            "Token过期": ToeknExpiredException("Token expired!"),
        }
        raise err_type_map.get(err_msg, Exception(err_msg))


def _parse_image_data_from_response_json(resp: dict) -> Tuple[bytes, str]:
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
        return image_data, mime_type

    # 无图时，返回占位符图片
    text_parts = [part.get("text", "") for part in parts]
    if any(text_parts):
        return _create_placeholder_image()
    raise GeminiAPIError("No image data found in API response")


def _create_placeholder_image() -> Tuple[bytes, str]:
    try:
        width, height = 100, 100
        png_data = _create_empty_image(width, height, (0, 100, 200))
        return png_data, "image/png"
    except Exception as e:
        raise GeminiAPIError(f"Failed to create placeholder: {str(e)}")


def _create_empty_image(width: int, height: int, color: tuple) -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".png") as f:
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
