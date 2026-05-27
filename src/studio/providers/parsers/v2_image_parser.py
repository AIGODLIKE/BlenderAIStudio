"""V2 图像生成响应解析器

解析 /v2/service/image 的响应格式：
{
    "responseId": "...",
    "code": 0,
    "data": {
        "reqId1": "taskId1",
        "reqId2": "taskId2"
    }
}

由于 v2 API 是异步的（返回 taskId 而非图片数据），
解析器会抛出特定异常以触发异步任务状态轮询。
"""

import logging
import requests

from .base import ResponseParser
from .utils import _check_response_account_mode
from ...exception import StudioException

try:
    from ....logger import logger
except Exception:
    logger = logging.getLogger(__name__)


class V2ImageSubmittedException(StudioException):
    """V2 任务已提交异常

    用于通知上层任务已异步提交，需要通过轮询获取结果。
    """

    def __init__(self, task_id_map: dict[str, str]):
        self.task_id_map = task_id_map
        super().__init__("Task is submitted, please wait for the result")


class V2ImageParser(ResponseParser):
    """V2 图像生成响应解析器

    解析 /v2/service/image 的响应，提取 reqId -> taskId 映射。
    由于 v2 是异步接口，解析成功后抛出 V2ImageSubmittedException，
    触发现有的异步任务状态轮询机制。
    """

    def parse(self, response: requests.Response):
        """解析 V2 响应

        Args:
            response: HTTP 响应

        Raises:
            V2ImageSubmittedException: 任务提交成功，需要异步等待结果
            Exception: 提交失败
        """
        self._check_response(response)

        resp_json = response.json()
        logger.info(f"V2 image response: {resp_json}")

        # 检查业务错误
        _check_response_account_mode(resp_json)

        # 提取 data（Map<ReqId, TaskId>）
        data = resp_json.get("data")
        if not isinstance(data, dict) or not data:
            raise V2ImageAPIError("Invalid V2 response: missing task ID mapping")

        logger.info(f"V2 image tasks submitted: {data}")

        # 抛出异常触发异步轮询
        raise V2ImageSubmittedException(data)

    def _check_response(self, response: requests.Response) -> None:
        code = response.status_code
        if code == 200:
            return
        if code in (401, 403):
            raise V2ImageAPIError("Authentication failed or token expired.")
        if code == 429:
            raise V2ImageAPIError("Rate limit exceeded.")
        if code == 400:
            logger.debug(getattr(response, "text", ""))
            raise V2ImageAPIError("Bad request (400)")
        if code == 502:
            raise V2ImageAPIError("Server Error: Bad Gateway.")
        try:
            j = response.json()
            if isinstance(j, dict) and "errMsg" in j:
                raise V2ImageAPIError(j["errMsg"])
        except V2ImageAPIError:
            raise
        except Exception:
            pass
        raise V2ImageAPIError(f"API request failed with status {code}")


class V2ImageAPIError(StudioException):
    pass
