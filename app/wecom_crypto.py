import base64
import hashlib
import os
import struct
from Crypto.Cipher import AES


BLOCK_SIZE = 32


class WeComCryptoError(Exception):
    pass


def sha1_signature(token: str, timestamp: str, nonce: str, encrypted: str) -> str:
    items = [token, timestamp, nonce, encrypted]
    items.sort()
    joined = ''.join(items)
    return hashlib.sha1(joined.encode('utf-8')).hexdigest()


def _pkcs7_pad(data: bytes) -> bytes:
    pad_len = BLOCK_SIZE - (len(data) % BLOCK_SIZE)
    if pad_len == 0:
        pad_len = BLOCK_SIZE
    return data + bytes([pad_len] * pad_len)


def _pkcs7_unpad(data: bytes) -> bytes:
    if not data:
        raise WeComCryptoError('empty decrypted payload')
    pad_len = data[-1]
    if pad_len < 1 or pad_len > BLOCK_SIZE:
        raise WeComCryptoError('invalid padding')
    return data[:-pad_len]


class WeComCrypto:
    def __init__(self, token: str, encoding_aes_key: str, corp_id: str):
        self.token = token
        self.corp_id = corp_id

        key = encoding_aes_key + '='
        self.aes_key = base64.b64decode(key)
        if len(self.aes_key) != 32:
            raise ValueError('encoding_aes_key invalid length')
        self.iv = self.aes_key[:16]

    def verify_signature(self, signature: str, timestamp: str, nonce: str, encrypted: str) -> None:
        local_sig = sha1_signature(self.token, timestamp, nonce, encrypted)
        if local_sig != signature:
            raise WeComCryptoError('signature mismatch')

    def encrypt(self, plain_text: str, nonce: str, timestamp: str) -> tuple[str, str]:
        plain_bytes = plain_text.encode('utf-8')
        random_16 = os.urandom(16)
        msg_len = struct.pack('!I', len(plain_bytes))
        payload = random_16 + msg_len + plain_bytes + self.corp_id.encode('utf-8')
        padded = _pkcs7_pad(payload)

        cipher = AES.new(self.aes_key, AES.MODE_CBC, self.iv)
        encrypted = base64.b64encode(cipher.encrypt(padded)).decode('utf-8')
        signature = sha1_signature(self.token, timestamp, nonce, encrypted)
        return encrypted, signature

    def decrypt(self, encrypted_b64: str) -> str:
        encrypted = base64.b64decode(encrypted_b64)
        cipher = AES.new(self.aes_key, AES.MODE_CBC, self.iv)
        plain_padded = cipher.decrypt(encrypted)
        plain = _pkcs7_unpad(plain_padded)

        msg_len = struct.unpack('!I', plain[16:20])[0]
        msg_start = 20
        msg_end = msg_start + msg_len
        msg = plain[msg_start:msg_end]
        recv_corp_id = plain[msg_end:].decode('utf-8')

        if recv_corp_id != self.corp_id:
            raise WeComCryptoError('corp_id mismatch')
        return msg.decode('utf-8')
