import json
import logging
import threading
import time
from hashlib import sha1
from pathlib import Path
from xml.etree import ElementTree as ET

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import PlainTextResponse

from app.access_control import resolve_access
from app.config import settings
from app.openclaw_bridge import OpenClawBridgeError, ask_openclaw
from app.wecom_api import WeComApiError, send_text_message
from app.wecom_crypto import WeComCrypto, WeComCryptoError

app = FastAPI(title='WeCom Callback Service', version='1.1.0')
crypto = WeComCrypto(
    token=settings.wecom_token,
    encoding_aes_key=settings.wecom_encoding_aes_key,
    corp_id=settings.wecom_corp_id,
)

logger = logging.getLogger('wecom_bridge')
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format='%(message)s')

_processed_events: dict[str, float] = {}
_processed_events_lock = threading.Lock()
_processed_ttl_seconds = 600

_user_state_file = Path('/root/.openclaw/workspace/user_state.json')
_user_state_lock = threading.Lock()


def _log(event: str, **kwargs) -> None:
    payload = {'event': event, 'ts': int(time.time())}
    payload.update(kwargs)
    logger.info(json.dumps(payload, ensure_ascii=False))


def _build_event_key(msg_root: ET.Element, from_user: str, content: str) -> str:
    msg_id = msg_root.findtext('MsgId', '')
    if msg_id:
        return f'msgid:{msg_id}'
    create_time = msg_root.findtext('CreateTime', '')
    digest = sha1(content.encode('utf-8')).hexdigest()[:12]
    return f'fallback:{from_user}:{create_time}:{digest}'


def _is_duplicate_event(event_key: str) -> bool:
    now = time.time()
    with _processed_events_lock:
        # cleanup expired entries
        expired = [k for k, ts in _processed_events.items() if now - ts > _processed_ttl_seconds]
        for k in expired:
            _processed_events.pop(k, None)

        if event_key in _processed_events:
            return True
        _processed_events[event_key] = now
        return False


def _load_user_state() -> dict:
    if not _user_state_file.exists():
        return {'welcomed_users': []}
    try:
        return json.loads(_user_state_file.read_text(encoding='utf-8'))
    except Exception:
        return {'welcomed_users': []}


def _mark_and_check_first_time_user(user_id: str) -> bool:
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
    for attempt in range(1, max_attempts + 1):
        try:
            send_text_message(to_user=to_user, content=content)
            _log('push_send_ok', to_user=to_user, attempt=attempt)
            return True
        except WeComApiError as exc:
            _log('push_send_fail', to_user=to_user, attempt=attempt, error=str(exc))
            if attempt < max_attempts:
                time.sleep(2 ** attempt)
    return False


@app.get('/healthz')
def healthz() -> dict[str, str]:
    return {'status': 'ok'}


@app.get('/wecom/callback', response_class=PlainTextResponse)
def verify_url(msg_signature: str, timestamp: str, nonce: str, echostr: str) -> str:
    try:
        crypto.verify_signature(msg_signature, timestamp, nonce, echostr)
        return crypto.decrypt(echostr)
    except WeComCryptoError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@app.post('/wecom/callback')
async def receive_message(request: Request, msg_signature: str, timestamp: str, nonce: str) -> Response:
    body = await request.body()
    try:
        req_root = ET.fromstring(body.decode('utf-8'))
        encrypted = req_root.findtext('Encrypt')
        if not encrypted:
            raise WeComCryptoError('missing Encrypt field')

        crypto.verify_signature(msg_signature, timestamp, nonce, encrypted)
        raw_xml = crypto.decrypt(encrypted)

        msg_root = ET.fromstring(raw_xml)
        from_user = msg_root.findtext('FromUserName', '')
        to_user = msg_root.findtext('ToUserName', '')
        msg_type = msg_root.findtext('MsgType', '')
        content = msg_root.findtext('Content', '')
        event_key = _build_event_key(msg_root, from_user, content)

        _log('incoming', from_user=from_user, msg_type=msg_type, event_key=event_key)

        if msg_type == 'text':
            if _is_duplicate_event(event_key):
                _log('duplicate_dropped', from_user=from_user, event_key=event_key)
                reply_text = '消息处理中，请勿重复发送。'
            else:
                decision = resolve_access(from_user)
                if not decision.allowed:
                    reply_text = settings.openclaw_no_access_reply
                    _log('access_denied', from_user=from_user, reason=decision.reason)
                else:
                    threading.Thread(
                        target=_process_and_push_reply,
                        args=(from_user, content, decision.workspace_dir, decision.agent_id),
                        daemon=True,
                    ).start()
                    reply_text = '已收到，正在处理中…'
        else:
            reply_text = f'已收到 {msg_type} 类型消息。'

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
    start = time.time()
    first_time = _mark_and_check_first_time_user(from_user)

    try:
        reply_text = ask_openclaw(
            wecom_user_id=from_user,
            message=content,
            workspace_dir=workspace_dir,
            agent_id=agent_id,
        )
    except OpenClawBridgeError:
        reply_text = '我这边处理超时了，请稍后再试一次。'

    if first_time:
        reply_text = '欢迎开通专属Agent服务！后续你的会话与工作空间都是独立隔离的。\n\n' + reply_text

    ok = _send_with_retry(to_user=from_user, content=reply_text, max_attempts=3)
    _log('process_done', from_user=from_user, agent_id=agent_id, elapsed_ms=int((time.time() - start) * 1000), pushed=ok)


def build_reply_xml(from_user: str, to_user: str, content: str) -> str:
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
    return (
        '<xml>'
        f'<Encrypt><![CDATA[{encrypt}]]></Encrypt>'
        f'<MsgSignature><![CDATA[{signature}]]></MsgSignature>'
        f'<TimeStamp>{timestamp}</TimeStamp>'
        f'<Nonce><![CDATA[{nonce}]]></Nonce>'
        '</xml>'
    )
