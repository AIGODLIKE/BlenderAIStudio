import requests
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

# 重试策略配置
RETRY_TOTAL = 5
RETRY_STATUS_FORCELIST = [429, 500, 502, 503, 504]
RETRY_ALLOWED_METHODS = ["HEAD", "GET", "PUT", "DELETE", "OPTIONS", "TRACE"]
RETRY_BACKOFF_FACTOR = 0.5

RETRY_STRATEGY = Retry(
    total=RETRY_TOTAL,
    status_forcelist=RETRY_STATUS_FORCELIST,
    allowed_methods=RETRY_ALLOWED_METHODS,
    backoff_factor=RETRY_BACKOFF_FACTOR,
)

# HTTP 适配器
ADAPTER = HTTPAdapter(max_retries=RETRY_STRATEGY)


def get_session() -> requests.Session:
    """
    支持重试策略的 HTTP Session 工厂函数
    """
    session = requests.Session()
    session.mount("https://", ADAPTER)
    session.mount("http://", ADAPTER)
    return session
