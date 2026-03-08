"""企业微信 ↔ OpenClaw 桥接主入口。

核心流程：
1) 企微回调验签/解密
2) ACL 鉴权 + 用户隔离路由
3) 异步调用 OpenClaw
4) 主动推送最终结果给用户

稳定性增强：
- 消息去重
- 失败重试
- 结构化日志
- 首次欢迎语
"""

import json
import logging
import threading
import time
from hashlib import sha1
from pathlib import Path
from xml.etree import ElementTree as ET

from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import PlainTextResponse

from app.access_control import resolve_access
from app.config import settings
from app.openclaw_bridge import OpenClawBridgeError, ask_openclaw
from app.wecom_api import WeComApiError, send_text_message
from app.wecom_crypto import WeComCrypto, WeComCryptoError

# FastAPI 应用实例
app = FastAPI(title='WeCom Callback Service', version='1.1.0')

# 企业微信加解密器（启动时基于配置初始化）
crypto = WeComCrypto(
    token=settings.wecom_token,
    encoding_aes_key=settings.wecom_encoding_aes_key,
    corp_id=settings.wecom_corp_id,
)

# 日志器：统一输出 JSON 结构化日志，便于检索和告警
logger = logging.getLogger('wecom_bridge')
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format='%(message)s')

# ====== 内存去重缓存 ======
# key: 事件唯一键（MsgId 或 fallback）
# val: 首次处理时间戳
_processed_events: dict[str, float] = {}
_processed_events_lock = threading.Lock()
_processed_ttl_seconds = 600  # 去重窗口（秒）

# ====== 用户欢迎状态 ======
# 记录哪些用户已发过“首次欢迎语”，防止每次都发
_user_state_file = Path('/root/.openclaw/workspace/user_state.json')
_user_state_lock = threading.Lock()


def _log(event: str, **kwargs) -> None:
    """输出结构化日志。"""
    payload = {'event': event, 'ts': int(time.time())}
    payload.update(kwargs)
    logger.info(json.dumps(payload, ensure_ascii=False))


def _build_event_key(msg_root: ET.Element, from_user: str, content: str) -> str:
    """构建消息去重键。

    优先使用企业微信 MsgId；若没有 MsgId（某些事件类型），
    用 from_user + create_time + 内容摘要 做兜底。
    """
    msg_id = msg_root.findtext('MsgId', '')
    if msg_id:
        return f'msgid:{msg_id}'

    create_time = msg_root.findtext('CreateTime', '')
    digest = sha1(content.encode('utf-8')).hexdigest()[:12]
    return f'fallback:{from_user}:{create_time}:{digest}'


def _is_duplicate_event(event_key: str) -> bool:
    """判断是否重复消息，并做过期清理。"""
    now = time.time()
    with _processed_events_lock:
        # 清理过期条目，避免缓存无限增长
        expired = [k for k, ts in _processed_events.items() if now - ts > _processed_ttl_seconds]
        for k in expired:
            _processed_events.pop(k, None)

        # 命中则为重复
        if event_key in _processed_events:
            return True

        # 首次出现，写入缓存
        _processed_events[event_key] = now
        return False


def _load_user_state() -> dict:
    """加载用户状态文件（用于首次欢迎语判定）。"""
    if not _user_state_file.exists():
        return {'welcomed_users': []}

    try:
        return json.loads(_user_state_file.read_text(encoding='utf-8'))
    except Exception:
        # 文件损坏时兜底为空，避免主流程中断
        return {'welcomed_users': []}


def _mark_and_check_first_time_user(user_id: str) -> bool:
    """标记并判断是否首次用户。"""
    with _user_state_lock:
        state = _load_user_state()
        welcomed = set(state.get('welcomed_users', []))

        if user_id in welcomed:
            return False

        welcomed.add(user_id)
        state['welcomed_users'] = sorted(welcomed)
        _user_state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        return True


def _send_with_retry(to_user: str, content: str, max_attempts: int = 3) -> bool:
    """主动发送企微消息（带重试）。

    重试策略：指数退避（2s, 4s, ...）
    """
    for attempt in range(1, max_attempts + 1):
        try:
            send_text_message(to_user=to_user, content=content)
            _log('push_send_ok', to_user=to_user, attempt=attempt)
            return True
        except WeComApiError as exc:
            _log('push_send_fail', to_user=to_user, attempt=attempt, error=str(exc))
            if attempt < max_attempts:
                time.sleep(2**attempt)

    return False


def _resolve_wecom_user_by_agent_id(agent_id: str) -> str:
    """根据 agent_id 反查企微用户ID。"""
    try:
        acl = json.loads(Path(settings.openclaw_acl_file).read_text(encoding='utf-8'))
    except Exception:
        return ''

    users = acl.get('users', {}) if isinstance(acl, dict) else {}
    for user_id, item in users.items():
        if isinstance(item, dict) and item.get('agent_id') == agent_id and bool(item.get('enabled', True)):
            return user_id
    return ''


def _extract_cron_summary(payload: dict) -> str:
    """兼容不同 webhook 结构，尽量提取人类可读摘要。"""
    if not isinstance(payload, dict):
        return ''
    for key in ('summary', 'text', 'message'):
        val = payload.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()

    run = payload.get('run')
    if isinstance(run, dict):
        for key in ('summary', 'text', 'message'):
            val = run.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    return ''


@app.get('/healthz')
def healthz() -> dict[str, str]:
    """健康检查接口。"""
    return {'status': 'ok'}


@app.post('/cron/deliver')
async def cron_deliver(request: Request, x_cron_token: str = Header(default='')) -> dict[str, object]:
    """接收 cron webhook，并按创建任务的 agent 回推到对应企微用户。

    约定：webhook body 至少包含 `agentId`（或 `agent_id`）与 `summary`（可选）。
    """
    token = settings.cron_webhook_token.strip()
    query_token = str(request.query_params.get('token', '')).strip()
    if token and x_cron_token.strip() != token and query_token != token:
        raise HTTPException(status_code=401, detail='invalid cron token')

    payload = await request.json()
    agent_id = str(payload.get('agentId') or payload.get('agent_id') or '').strip()
    if not agent_id:
        raise HTTPException(status_code=400, detail='missing agentId')

    user_id = _resolve_wecom_user_by_agent_id(agent_id)
    if not user_id:
        raise HTTPException(status_code=404, detail='agent not bound to enabled wecom user')

    summary = _extract_cron_summary(payload)
    if not summary:
        summary = '提醒任务已执行完成。'

    ok = _send_with_retry(to_user=user_id, content=summary, max_attempts=3)
    _log('cron_deliver', agent_id=agent_id, to_user=user_id, pushed=ok)
    if not ok:
        raise HTTPException(status_code=502, detail='push failed')
    return {'ok': True, 'agent_id': agent_id, 'to_user': user_id}


@app.get('/wecom/callback', response_class=PlainTextResponse)
def verify_url(msg_signature: str, timestamp: str, nonce: str, echostr: str) -> str:
    """企业微信“保存并验证”时的 URL 校验接口。"""
    try:
        crypto.verify_signature(msg_signature, timestamp, nonce, echostr)
        return crypto.decrypt(echostr)
    except WeComCryptoError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@app.post('/wecom/callback')
async def receive_message(request: Request, msg_signature: str, timestamp: str, nonce: str) -> Response:
    """企业微信消息回调入口。"""
    body = await request.body()
    try:
        # 1) 解析外层 XML（含 Encrypt）
        req_root = ET.fromstring(body.decode('utf-8'))
        encrypted = req_root.findtext('Encrypt')
        if not encrypted:
            raise WeComCryptoError('missing Encrypt field')

        # 2) 验签 + 解密
        crypto.verify_signature(msg_signature, timestamp, nonce, encrypted)
        raw_xml = crypto.decrypt(encrypted)

        # 3) 解析明文消息
        msg_root = ET.fromstring(raw_xml)
        from_user = msg_root.findtext('FromUserName', '')
        to_user = msg_root.findtext('ToUserName', '')
        msg_type = msg_root.findtext('MsgType', '')
        content = msg_root.findtext('Content', '')
        event_key = _build_event_key(msg_root, from_user, content)

        _log('incoming', from_user=from_user, msg_type=msg_type, event_key=event_key)

        # 4) 按消息类型处理（当前重点是文本）
        if msg_type == 'text':
            # 4.1 去重：丢弃重复投递
            if _is_duplicate_event(event_key):
                _log('duplicate_dropped', from_user=from_user, event_key=event_key)
                reply_text = '消息处理中，请勿重复发送。'
            else:
                # 4.2 ACL 访问控制
                decision = resolve_access(from_user)
                if not decision.allowed:
                    reply_text = settings.openclaw_no_access_reply
                    _log('access_denied', from_user=from_user, reason=decision.reason)
                else:
                    # 4.3 异步处理：避免被动回调超时
                    threading.Thread(
                        target=_process_and_push_reply,
                        args=(from_user, content, decision.workspace_dir, decision.agent_id),
                        daemon=True,
                    ).start()
                    reply_text = '已收到，正在处理中…'
        else:
            # 非文本先做基础提示（可后续扩展语音/图片等）
            reply_text = f'已收到 {msg_type} 类型消息。'

        # 5) 被动回复（加密后返回给企微）
        reply_xml = build_reply_xml(from_user=from_user, to_user=to_user, content=reply_text)
        now = str(int(time.time()))
        encrypted_reply, signature = crypto.encrypt(reply_xml, nonce=nonce, timestamp=now)
        resp_xml = build_encrypted_xml(encrypt=encrypted_reply, signature=signature, timestamp=now, nonce=nonce)
        return Response(content=resp_xml, media_type='application/xml')

    except WeComCryptoError as exc:
        _log('crypto_error', error=str(exc))
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except ET.ParseError as exc:
        _log('parse_error', error=str(exc))
        raise HTTPException(status_code=400, detail='invalid xml body') from exc


def _process_and_push_reply(from_user: str, content: str, workspace_dir: str, agent_id: str) -> None:
    """后台异步任务：调用 OpenClaw 并主动推送最终结果。"""
    start = time.time()
    first_time = _mark_and_check_first_time_user(from_user)

    # 1) 调用 OpenClaw
    try:
        reply_text = ask_openclaw(
            wecom_user_id=from_user,
            message=content,
            workspace_dir=workspace_dir,
            agent_id=agent_id,
        )
    except OpenClawBridgeError:
        reply_text = '我这边处理超时了，请稍后再试一次。'

    # 2) 首次用户体验增强：追加欢迎语
    if first_time:
        reply_text = '欢迎开通专属Agent服务！后续你的会话与工作空间都是独立隔离的。\n\n' + reply_text

    # 3) 主动推送（失败自动重试）
    ok = _send_with_retry(to_user=from_user, content=reply_text, max_attempts=3)
    _log('process_done', from_user=from_user, agent_id=agent_id, elapsed_ms=int((time.time() - start) * 1000), pushed=ok)


def build_reply_xml(from_user: str, to_user: str, content: str) -> str:
    """构造企微被动回复 XML。"""
    create_time = int(time.time())
    return (
        '<xml>'
        f'<ToUserName><![CDATA[{from_user}]]></ToUserName>'
        f'<FromUserName><![CDATA[{to_user}]]></FromUserName>'
        f'<CreateTime>{create_time}</CreateTime>'
        '<MsgType><![CDATA[text]]></MsgType>'
        f'<Content><![CDATA[{content}]]></Content>'
        f'<AgentID>{settings.wecom_agent_id}</AgentID>'
        '</xml>'
    )


def build_encrypted_xml(encrypt: str, signature: str, timestamp: str, nonce: str) -> str:
    """构造企微要求的加密响应 XML 外层结构。"""
    return (
        '<xml>'
        f'<Encrypt><![CDATA[{encrypt}]]></Encrypt>'
        f'<MsgSignature><![CDATA[{signature}]]></MsgSignature>'
        f'<TimeStamp>{timestamp}</TimeStamp>'
        f'<Nonce><![CDATA[{nonce}]]></Nonce>'
        '</xml>'
    )
