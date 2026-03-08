"""企业微信回调加解密工具。

实现内容：
- SHA1 签名校验
- PKCS7 补位/去补位
- AES-CBC 加密与解密（企业微信协议）
"""

import base64
import hashlib
import os
import struct

from Crypto.Cipher import AES


# 企业微信协议固定使用 32 字节块大小
BLOCK_SIZE = 32


class WeComCryptoError(Exception):
    """企业微信加解密相关异常。"""


def sha1_signature(token: str, timestamp: str, nonce: str, encrypted: str) -> str:
    """按企微规则计算签名：字典序排序后拼接，再做 SHA1。"""
    items = [token, timestamp, nonce, encrypted]
    items.sort()
    joined = ''.join(items)
    return hashlib.sha1(joined.encode('utf-8')).hexdigest()


def _pkcs7_pad(data: bytes) -> bytes:
    """PKCS7 补位。"""
    pad_len = BLOCK_SIZE - (len(data) % BLOCK_SIZE)
    if pad_len == 0:
        pad_len = BLOCK_SIZE
    return data + bytes([pad_len] * pad_len)


def _pkcs7_unpad(data: bytes) -> bytes:
    """PKCS7 去补位，并做基本合法性校验。"""
    if not data:
        raise WeComCryptoError('empty decrypted payload')
    pad_len = data[-1]
    if pad_len < 1 or pad_len > BLOCK_SIZE:
        raise WeComCryptoError('invalid padding')
    return data[:-pad_len]


class WeComCrypto:
    """企业微信回调加解密器。"""

    def __init__(self, token: str, encoding_aes_key: str, corp_id: str):
        self.token = token
        self.corp_id = corp_id

        # 企业微信给的是 43 位 base64，解码前需补 '='
        key = encoding_aes_key + '='
        self.aes_key = base64.b64decode(key)
        if len(self.aes_key) != 32:
            raise ValueError('encoding_aes_key invalid length')

        # AES-CBC IV 为 key 前 16 字节
        self.iv = self.aes_key[:16]

    def verify_signature(self, signature: str, timestamp: str, nonce: str, encrypted: str) -> None:
        """校验签名，不通过则抛异常。"""
        local_sig = sha1_signature(self.token, timestamp, nonce, encrypted)
        if local_sig != signature:
            raise WeComCryptoError('signature mismatch')

    def encrypt(self, plain_text: str, nonce: str, timestamp: str) -> tuple[str, str]:
        """加密明文并返回 (encrypted_b64, signature)。"""
        plain_bytes = plain_text.encode('utf-8')

        # 协议格式：16随机字节 + 4字节明文长度 + 明文 + corp_id
        random_16 = os.urandom(16)
        msg_len = struct.pack('!I', len(plain_bytes))
        payload = random_16 + msg_len + plain_bytes + self.corp_id.encode('utf-8')
        padded = _pkcs7_pad(payload)

        cipher = AES.new(self.aes_key, AES.MODE_CBC, self.iv)
        encrypted = base64.b64encode(cipher.encrypt(padded)).decode('utf-8')
        signature = sha1_signature(self.token, timestamp, nonce, encrypted)
        return encrypted, signature

    def decrypt(self, encrypted_b64: str) -> str:
        """解密企业微信密文并返回 UTF-8 明文。"""
        encrypted = base64.b64decode(encrypted_b64)
        cipher = AES.new(self.aes_key, AES.MODE_CBC, self.iv)
        plain_padded = cipher.decrypt(encrypted)
        plain = _pkcs7_unpad(plain_padded)

        # 反解协议格式
        msg_len = struct.unpack('!I', plain[16:20])[0]
        msg_start = 20
        msg_end = msg_start + msg_len
        msg = plain[msg_start:msg_end]
        recv_corp_id = plain[msg_end:].decode('utf-8')

        # corp_id 校验，防止串租户
        if recv_corp_id != self.corp_id:
            raise WeComCryptoError('corp_id mismatch')

        return msg.decode('utf-8')
