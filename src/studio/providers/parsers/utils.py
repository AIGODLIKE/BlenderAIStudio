from ...exception import (
    InsufficientBalanceException,
    APIRequestException,
    AuthFailedException,
    ToeknExpiredException,
)


def _check_response_account_mode(resp: dict):
    """
    {
        'responseId': ...,
        'code': -4,
        'errCode': -4000,
        'errMsg': 'xxx',
    }

    code[-1 -> -1201] -- 余额不足
    code[-1 -> -1201] -- API请求错误!
    code[-3 -> -3002] -- 数据库更新错误（不需要展示）
    code[-4 -> -4000] -- 鉴权错误
    code[-4 -> -4001] -- Token过期
    """
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
    raise err_type_map.get(err_msg, Exception(err_msg))
