"""企业微信主动消息 API 封装。

职责：
1) 获取并缓存 access_token
2) 发送文本消息
"""

import json
import threading
import time
from urllib import parse, request

from app.config import settings


class WeComApiError(Exception):
    """企业微信 API 调用异常。"""


# token 缓存与并发锁（避免高并发下重复拉 token）
_token_lock = threading.Lock()
_cached_token = ''
_token_expire_at = 0.0


def _http_get_json(url: str) -> dict:
    """发送 GET 请求并返回 JSON。"""
    with request.urlopen(url, timeout=8) as resp:
        return json.loads(resp.read().decode('utf-8'))


def _http_post_json(url: str, payload: dict) -> dict:
    """发送 POST(JSON) 请求并返回 JSON。"""
    data = json.dumps(payload).encode('utf-8')
    req = request.Request(url, data=data, method='POST')
    req.add_header('Content-Type', 'application/json')
    with request.urlopen(req, timeout=8) as resp:
        return json.loads(resp.read().decode('utf-8'))


def get_access_token() -> str:
    """获取企业微信 access_token（带内存缓存）。"""
    global _cached_token, _token_expire_at

    now = time.time()
    if _cached_token and now < _token_expire_at:
        return _cached_token

    with _token_lock:
        # 双重检查：减少锁竞争
        now = time.time()
        if _cached_token and now < _token_expire_at:
            return _cached_token

        # 调用企业微信 gettoken 接口
        url = (
            'https://qyapi.weixin.qq.com/cgi-bin/gettoken?'
            + parse.urlencode({'corpid': settings.wecom_corp_id, 'corpsecret': settings.wecom_secret})
        )
        data = _http_get_json(url)
        if data.get('errcode') != 0:
            raise WeComApiError(f"gettoken failed: {data}")

        _cached_token = data['access_token']
        expires_in = int(data.get('expires_in', 7200))
        # 提前 120 秒过期，避免边界时刻请求失败
        _token_expire_at = time.time() + max(60, expires_in - 120)
        return _cached_token


def send_text_message(to_user: str, content: str) -> None:
    """向指定企微用户发送文本消息。"""
    token = get_access_token()
    url = 'https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token=' + token

    payload = {
        'touser': to_user,
        'msgtype': 'text',
        'agentid': settings.wecom_agent_id,
        'text': {'content': content[:2000]},  # 文本长度做上限保护
        'safe': 0,
    }
    data = _http_post_json(url, payload)
    if data.get('errcode') != 0:
        raise WeComApiError(f"message send failed: {data}")
