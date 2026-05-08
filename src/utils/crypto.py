"""AES 加密工具。

用于 XBOX 账号密码（必须可逆,因为 Microsoft 登录要明文）。

设计：
- AES-256-GCM（带认证,防篡改）
- 密钥从环境变量 ``XBOX_ACCOUNT_PASSWORD_KEY`` 读（base64 编码的 32 字节）
- 密文格式：``base64(nonce[12] + ciphertext + tag[16])``
- 解密失败抛 ``CryptoError``

密钥管理：
1. 首次部署：``python -c "import os, base64; print(base64.b64encode(os.urandom(32)).decode())"``
2. 把输出写到 ``.env`` 里 ``XBOX_ACCOUNT_PASSWORD_KEY=...``
3. ``.env`` 已 .gitignore,绝不提交
"""
from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class CryptoError(Exception):
    """加密 / 解密失败。"""


_KEY_ENV_VAR = "XBOX_ACCOUNT_PASSWORD_KEY"


def _load_key() -> bytes:
    """从环境变量加载 AES key。base64 编码的 32 字节。"""
    raw = os.environ.get(_KEY_ENV_VAR)
    if not raw:
        raise CryptoError(
            f"环境变量 {_KEY_ENV_VAR} 未设置；运行 "
            f"python -c \"import os, base64; print(base64.b64encode(os.urandom(32)).decode())\" "
            f"生成一个 32 字节 base64 密钥写到 .env"
        )
    try:
        key = base64.b64decode(raw)
    except Exception as exc:
        raise CryptoError(f"{_KEY_ENV_VAR} 不是合法 base64: {exc}") from exc
    if len(key) != 32:
        raise CryptoError(f"{_KEY_ENV_VAR} 解码后必须 32 字节,实际 {len(key)}")
    return key


def encrypt_password(plaintext: str) -> str:
    """加密明文密码,返回 base64 字符串（含 nonce + 密文 + 认证 tag）。"""
    if plaintext is None:
        raise CryptoError("明文不能为 None")
    key = _load_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    return base64.b64encode(nonce + ciphertext).decode("ascii")


def decrypt_password(ciphertext_b64: str) -> str:
    """解密成明文密码。失败抛 CryptoError。"""
    if not ciphertext_b64:
        raise CryptoError("密文不能为空")
    key = _load_key()
    try:
        blob = base64.b64decode(ciphertext_b64)
    except Exception as exc:
        raise CryptoError(f"密文不是合法 base64: {exc}") from exc
    if len(blob) < 12 + 16:
        raise CryptoError(f"密文长度不足: {len(blob)}")
    nonce, ciphertext = blob[:12], blob[12:]
    aesgcm = AESGCM(key)
    try:
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)
    except Exception as exc:
        raise CryptoError(f"解密失败（密钥不对或密文被篡改）: {exc}") from exc
    return plaintext.decode("utf-8")


def generate_key_for_setup() -> str:
    """生成新 base64 密钥（仅用于初次部署/文档示例,不在业务逻辑里调用）。"""
    return base64.b64encode(os.urandom(32)).decode("ascii")
