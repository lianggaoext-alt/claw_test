import time
from xml.etree import ElementTree as ET
 
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import PlainTextResponse

from app.config import settings
from app.openclaw_bridge import OpenClawBridgeError, ask_openclaw
from app.wecom_crypto import WeComCrypto, WeComCryptoError

app = FastAPI(title='WeCom Callback Service', version='1.0.0')
crypto = WeComCrypto(
    token=settings.wecom_token,
    encoding_aes_key=settings.wecom_encoding_aes_key,
    corp_id=settings.wecom_corp_id,
)


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

        if msg_type == 'text':
            try:
                reply_text = ask_openclaw(wecom_user_id=from_user, message=content)
            except OpenClawBridgeError as exc:
                reply_text = f'服务暂时不可用：{exc}'
        else:
            reply_text = f'已收到 {msg_type} 类型消息，当前仅自动回文本。'

        reply_xml = build_reply_xml(from_user=from_user, to_user=to_user, content=reply_text)
        now = str(int(time.time()))
        encrypted_reply, signature = crypto.encrypt(reply_xml, nonce=nonce, timestamp=now)
        resp_xml = build_encrypted_xml(encrypt=encrypted_reply, signature=signature, timestamp=now, nonce=nonce)
        return Response(content=resp_xml, media_type='application/xml')
    except WeComCryptoError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except ET.ParseError as exc:
        raise HTTPException(status_code=400, detail='invalid xml body') from exc


def build_reply_xml(from_user: str, to_user: str, content: str) -> str:
    create_time = int(time.time())
    return (
        '<xml>'
        f'<ToUserName><![CDATA[{from_user}]]></ToUserName>'
        f'<FromUserName><![CDATA[{to_user}]]></FromUserName>'
        f'<CreateTime>{create_time}</CreateTime>'
        '<MsgType><![CDATA[text]]></MsgType>'
        f'<Content><![CDATA[{content}]]></Content>'
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
