"""V2 图像生成请求构建器

统一所有图像生成模型的 account 模式提交流程：
1. 委托原始 Builder 构建 payload（含 base64 图片）
2. 从 payload 中提取图片数据，上传到 OSS
3. 将去除图片后的 payload 序列化为 originalPayloadJson
4. 包装为 ServiceV2ImageGenBo 格式提交到 /v2/service/image
"""

import base64
import copy
import datetime
import hashlib
import hmac
import json
import mimetypes
import os
import requests

from pathlib import Path
from typing import Any, TYPE_CHECKING
from bpy.app.translations import pgettext as _T

from .base import RequestBuilder, RequestData
from .registry import BuilderRegistry
from ..parsers.utils import _check_response_account_mode
from ...config.url_config import URLConfigManager
from .... import logger
from ....utils.image_processor import ImageProcessor

if TYPE_CHECKING:
    from ...config.model_registry import ModelConfig


class V2ImageBuilder(RequestBuilder):
    """V2 图像生成构建器（account 模式专用）

    职责：
    - 委托内部 builder 构建原始 payload
    - 提取参考图片并上传到 OSS（获取 resourceSetId）
    - 将原始 payload（去除图片二进制）序列化为 originalPayloadJson
    - 构建 ServiceV2ImageGenBo 格式的最终请求
    """

    # OSS 配置
    OSS_BUCKET = "acggit-addon"
    OSS_REGION = "cn-beijing"
    OSS_ENDPOINT = f"https://{OSS_BUCKET}.oss-{OSS_REGION}.aliyuncs.com"
    OSS_OBJECT_ACL = "public-read"

    # pre-upload typeCode: 2 = 图像资源
    PRE_UPLOAD_TYPE_CODE = 2

    def __init__(self, inner_builder_name: str):
        """
        Args:
            inner_builder_name: 内部 builder 名称，用于构建原始 payload
        """
        self.inner_builder_name = inner_builder_name

    def build(
        self,
        params: dict[str, Any],
        model_config: "ModelConfig",
        auth_mode: str,
        credentials: dict[str, str],
    ) -> RequestData:
        # 1. 委托内部 builder 构建原始请求（含 base64 图片）
        inner_builder = BuilderRegistry.get(self.inner_builder_name)
        inner_request = inner_builder.build(params, model_config, auth_mode, credentials)

        # 2. 收集需要上传的图片文件路径（所有可能的图片来源）
        image_paths = self._collect_image_paths(params)

        # 3. 上传图片到 OSS（如果有图片）
        resource_set_id = None
        if image_paths:
            resource_set_id = self._upload_images_to_oss(image_paths, credentials)

        # 4. 构建 originalPayloadJson（原始 payload 去除图片数据后序列化）
        stripped_payload = self._strip_image_data_from_payload(inner_request.payload)
        original_payload_json = json.dumps(stripped_payload, ensure_ascii=False) if stripped_payload else "{}"

        # 5. 构建 ServiceV2ImageGenBo
        req_id = credentials.get("reqId", "")
        model_id = credentials.get("modelId", "")
        image_size = credentials.get("size", "1K")

        # modelId 需要是数字类型（Long）
        try:
            model_id_num = int(model_id)
        except (ValueError, TypeError):
            model_id_num = model_id

        v2_payload = {
            "reqId": [req_id],
            "modelId": model_id_num,
            "imageSize": image_size,
            "count": 1,
            "originalPayloadJson": original_payload_json,
        }
        if resource_set_id is not None:
            try:
                v2_payload["resourceSetId"] = int(resource_set_id)
            except (ValueError, TypeError):
                v2_payload["resourceSetId"] = resource_set_id

        # 6. 构建 v2 URL
        url = self._build_v2_url()

        # 7. 构建 headers
        headers = {
            "X-Auth-T": credentials.get("token", ""),
            "Content-Type": "application/json",
        }

        logger.info(f"V2 submit url: {url}")
        logger.info(f"V2 submit payload: {json.dumps(v2_payload, ensure_ascii=False)[:500]}")

        return RequestData(
            url=url,
            headers=headers,
            payload=v2_payload,
            method="POST",
            timeout=80,
        )

    # ==================== URL 构建 ====================

    def _build_v2_url(self) -> str:
        """构建 v2 API URL: {base}/v2/service/image"""
        url_manager = URLConfigManager.get_instance()
        base_url = url_manager.get_service_base_url()
        return f"{base_url}/v2/service/image"

    # ==================== OSS 上传 ====================

    def _upload_images_to_oss(
        self,
        image_paths: list[str],
        credentials: dict[str, str],
    ) -> int | None:
        """上传所有参考图片到 OSS 并返回 resourceSetId

        一次 pre-upload 请求获取一个 resourceSetId，
        所有图片上传到同一个 set 下，后端用 resourceSetId 重新拼接 payload。
        """
        prep = ImageProcessor.prepare_images_for_upload(image_paths)
        if not prep.paths:
            return None

        # 获取文件类型列表
        file_types = [self._guess_file_type(p) for p in prep.paths]

        # 请求 pre-upload（一次请求，获取所有文件的上传凭证）
        pre_upload_data = self._request_pre_upload(file_types, credentials)
        set_id = pre_upload_data.get("setId")
        upload_map = pre_upload_data.get("uploadMap") or {}

        # 按 image-N 排序解析上传目标
        upload_targets = self._resolve_upload_targets(upload_map, len(prep.paths))

        # 逐个上传
        for i, path in enumerate(prep.paths):
            if i >= len(upload_targets) or not upload_targets[i]:
                logger.warning(f"V2 upload: no upload target for image {i}, skipping")
                continue

            object_key = self._resolve_object_key(upload_targets[i])
            logger.info(f"V2 OSS upload [{i}/{len(prep.paths)}]: {object_key}")

            fields = self._build_oss_form_fields(
                bucket=self.OSS_BUCKET,
                region=self.OSS_REGION,
                object_key=object_key,
                access_key=pre_upload_data.get("ak", ""),
                secret_key=pre_upload_data.get("sk", ""),
                security_token=pre_upload_data.get("sts", ""),
            )

            boundary, body = self._build_multipart_body(path, fields)

            response = requests.post(
                self.OSS_ENDPOINT,
                data=body,
                headers={
                    "Content-Type": f"multipart/form-data; boundary={boundary}",
                    "Host": f"{self.OSS_BUCKET}.oss-{self.OSS_REGION}.aliyuncs.com",
                },
                timeout=300,
            )
            logger.info(f"V2 OSS upload response: status={response.status_code}, {response.text}")
            if not 200 <= response.status_code < 300:
                logger.error(f"V2 OSS upload failed: {response.text}")
                raise ValueError(_T("Image upload failed: HTTP {code}").format(code=response.status_code))

        return set_id

    def _request_pre_upload(
        self,
        file_types: list[str],
        credentials: dict[str, str],
    ) -> dict[str, Any]:
        """请求 pre-upload 接口获取 OSS 凭证"""
        url_manager = URLConfigManager.get_instance()
        base_url = url_manager.get_service_base_url()
        url = f"{base_url}/v1/resource/pre-upload"

        logger.info(f"V2 pre-upload url: {url} fileTypes: {file_types}")
        response = requests.post(
            url,
            headers={
                "X-Auth-T": credentials.get("token", ""),
                "Content-Type": "application/json",
            },
            json={
                "typeCode": self.PRE_UPLOAD_TYPE_CODE,
                "fileType": file_types,
                "resourceCount": len(file_types),
            },
            timeout=30,
        )
        response.raise_for_status()

        response_json = response.json()
        logger.info(f"V2 pre-upload response: {json.dumps(response_json, ensure_ascii=False)}")
        _check_response_account_mode(response_json)
        data = response_json.get("data") if isinstance(response_json, dict) else None

        if not isinstance(data, dict):
            raise ValueError(_T("Invalid pre-upload response."))
        if not data.get("setId"):
            raise ValueError(_T("Pre-upload response missing setId."))
        if not data.get("uploadMap"):
            raise ValueError(_T("Pre-upload response missing uploadMap."))
        return data

    # ==================== OSS 签名与表单构建 ====================

    def _build_oss_form_fields(
        self,
        bucket: str,
        region: str,
        object_key: str,
        access_key: str,
        secret_key: str,
        security_token: str,
    ) -> dict[str, str]:
        """构建 OSS PostObject 表单字段（OSS4-HMAC-SHA256 签名）"""
        if not access_key or not secret_key:
            raise ValueError(_T("Pre-upload response missing OSS credentials."))

        utc_now = datetime.datetime.now(datetime.timezone.utc)
        date_ymd = utc_now.strftime("%Y%m%d")
        x_oss_date = utc_now.strftime("%Y%m%dT%H%M%SZ")
        expiration = (utc_now + datetime.timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ")

        conditions: list[Any] = [
            {"bucket": bucket},
            {"key": object_key},
            {"x-oss-signature-version": "OSS4-HMAC-SHA256"},
            {"x-oss-credential": f"{access_key}/{date_ymd}/{region}/oss/aliyun_v4_request"},
            {"x-oss-date": x_oss_date},
            {"x-oss-object-acl": self.OSS_OBJECT_ACL},
            ["content-length-range", 1, 10 * 1024 * 1024],
        ]
        if security_token:
            conditions.append({"x-oss-security-token": security_token})

        policy = base64.b64encode(json.dumps({"expiration": expiration, "conditions": conditions}).encode("utf-8")).decode("utf-8")
        signature = self._sign_oss_policy(secret_key, region, policy, date_ymd)

        fields = {
            "key": object_key,
            "policy": policy,
            "x-oss-signature-version": "OSS4-HMAC-SHA256",
            "x-oss-credential": f"{access_key}/{date_ymd}/{region}/oss/aliyun_v4_request",
            "x-oss-date": x_oss_date,
            "x-oss-signature": signature,
            "x-oss-object-acl": self.OSS_OBJECT_ACL,
        }
        if security_token:
            fields["x-oss-security-token"] = security_token
        return fields

    def _sign_oss_policy(self, secret_key: str, region: str, policy: str, date_ymd: str) -> str:
        key_date = hmac.new(f"aliyun_v4{secret_key}".encode("utf-8"), date_ymd.encode("utf-8"), hashlib.sha256).digest()
        key_region = hmac.new(key_date, region.encode("utf-8"), hashlib.sha256).digest()
        key_service = hmac.new(key_region, b"oss", hashlib.sha256).digest()
        key_signing = hmac.new(key_service, b"aliyun_v4_request", hashlib.sha256).digest()
        return hmac.new(key_signing, policy.encode("utf-8"), hashlib.sha256).hexdigest()


    def _build_multipart_body(self, file_path: str, fields: dict[str, str]) -> tuple[str, bytes]:
        """构建 multipart/form-data 请求体"""
        boundary = "----WebKitFormBoundary" + base64.urlsafe_b64encode(os.urandom(12)).decode("utf-8")
        chunks: list[bytes] = []
        for key, value in fields.items():
            chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode("utf-8"))

        file_name = Path(file_path).name
        file_bytes = Path(file_path).read_bytes()
        chunks.append((f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{file_name}"\r\n\r\n').encode("utf-8") + file_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8"))
        return boundary, b"".join(chunks)

    # ==================== 辅助方法 ====================

    def _collect_image_paths(self, params: dict[str, Any]) -> list[str]:
        """从 params 中收集所有需要上传的图片路径

        兼容不同模型的参数命名：
        - main_image: InputProcessor 输出的主图
        - image_path: 旧版兼容
        - reference_images: 参考图列表
        - mask_path: 遮罩图
        """
        candidates: list[Any] = []
        # 主图（InputProcessor 输出）
        main_image = params.get("main_image")
        if main_image:
            candidates.append(main_image)
        # 旧版兼容
        image_path = params.get("image_path")
        if image_path:
            candidates.append(image_path)
        # 参考图列表
        ref_images = params.get("reference_images", [])
        if isinstance(ref_images, list):
            candidates.extend(ref_images)
        # 遮罩图
        mask_path = params.get("mask_path")
        if mask_path:
            candidates.append(mask_path)

        # 过滤：只保留存在的文件路径，去重保序
        seen: set[str] = set()
        paths: list[str] = []
        for item in candidates:
            if not item or not isinstance(item, str):
                continue
            if not Path(item).exists():
                continue
            if item not in seen:
                seen.add(item)
                paths.append(item)
        return paths

    def _resolve_object_key(self, upload_target: Any) -> str:
        """从 uploadMap 的 value 中解析 OSS object key"""
        if isinstance(upload_target, dict):
            raw = (
                upload_target.get("path")
                or upload_target.get("key")
                or upload_target.get("objectKey")
                or upload_target.get("url")
                or ""
            )
        else:
            raw = str(upload_target)

        raw = raw.strip().lstrip("/")
        if not raw:
            raise ValueError(_T("Unable to determine OSS object key."))
        return raw

    def _resolve_upload_targets(self, upload_map: dict, count: int) -> list:
        """从 uploadMap 中按顺序解析出上传目标列表

        typeCode=2 时 uploadMap 格式为：
        {"image-0": "xxx.png", "image-1": "yyy.png", ...}
        按 image-N 的数字后缀排序。
        """
        if not upload_map:
            return [None] * count

        def sort_key(k: str):
            parts = k.rsplit("-", 1)
            try:
                return int(parts[-1])
            except (ValueError, IndexError):
                return 0

        sorted_keys = sorted(upload_map.keys(), key=sort_key)
        return [upload_map[sorted_keys[i]] if i < len(sorted_keys) else None for i in range(count)]

    def _guess_file_type(self, image_path: str) -> str:
        """猜测文件类型"""
        suffix = Path(image_path).suffix.lower().lstrip(".")
        if suffix:
            return suffix
        mime_type = mimetypes.guess_type(image_path)[0]
        if mime_type:
            return mime_type.split("/", 1)[-1]
        return "png"

    def _strip_image_data_from_payload(self, payload: dict | None) -> dict:
        """从 payload 中移除图片相关的 parts/数据

        支持两种 payload 格式：
        - Gemini 格式：移除 contents[].parts[] 中包含 inline_data/inlineData 的整个 part
        - Seedream 格式：移除 image 列表

        后端会根据 resourceSetId 自行注入图片数据。
        """
        if not payload:
            return {}

        stripped = copy.deepcopy(payload)

        # Gemini 格式：移除包含 inline_data 的 part
        if "contents" in stripped:
            for content in stripped.get("contents", []):
                parts = content.get("parts", [])
                content["parts"] = [
                    part for part in parts
                    if "inline_data" not in part and "inlineData" not in part
                ]

        # Seedream 格式：移除 image 列表
        if "image" in stripped:
            del stripped["image"]

        return stripped
