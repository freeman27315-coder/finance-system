"""pytest 全局配置：设置测试用的环境变量。"""
from __future__ import annotations

import base64
import os


def _ensure_xbox_password_key() -> None:
    """测试用 AES key（固定 32 字节,base64 编码）。

    生产用的密钥从 .env 读,测试时如果没设就用一个稳定的 zero-key,
    保证 cryptography 不报错。CI 环境也走这条路。
    """
    if "XBOX_ACCOUNT_PASSWORD_KEY" in os.environ:
        return
    test_key = base64.b64encode(b"test-key-32-bytes!!!" + b"\x00" * 12).decode()
    os.environ["XBOX_ACCOUNT_PASSWORD_KEY"] = test_key


_ensure_xbox_password_key()
