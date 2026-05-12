"""客服认证服务: 注册 / 登录 / TOTP / JWT。

业务规则（CEO 2026-05-11 确认）:
- 客服账号(operators 表)独立于 XBOX 账号
- 登录三要素: login_name + password + TOTP 6 位
- 首次创建时生成 TOTP secret,客服扫码绑定后才能登录
- 密码 bcrypt 哈希; TOTP 用 Google Authenticator / Authy 任意 RFC 6238 兼容 App
- JWT token 给客服 exe / API 后续认证用,默认 12 小时有效
"""
from __future__ import annotations

import base64
import io
import os
from datetime import datetime, timedelta
from typing import Optional

import bcrypt
import pyotp
import qrcode
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.operator import Operator
from src.utils.time import china_now

# JWT 配置(密钥可从 env,简单起见用固定值,生产建议放 .env)
_JWT_SECRET = os.environ.get("OPERATOR_JWT_SECRET", "dev-jwt-secret-please-change-in-production")
_JWT_ALGORITHM = "HS256"
_JWT_EXPIRE_HOURS = 12

# TOTP App 显示的项目名
_TOTP_ISSUER = "Finance System (XBOX 客服)"


class AuthError(Exception):
    """认证失败(密码错/TOTP 错/账号停用等)。"""


# ---------------------------------------------------------------------------
# 密码 + TOTP
# ---------------------------------------------------------------------------

def hash_password(plain: str) -> str:
    """bcrypt 直接 API。bcrypt 限制 72 字节,超长 truncate(密码足够安全)。"""
    encoded = plain.encode("utf-8")[:72]
    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        encoded = plain.encode("utf-8")[:72]
        return bcrypt.checkpw(encoded, hashed.encode("ascii"))
    except Exception:
        return False


def generate_totp_secret() -> str:
    """生成新的 TOTP base32 密钥(20 字节,160 位)。"""
    return pyotp.random_base32()


def totp_provisioning_uri(secret: str, login_name: str) -> str:
    """生成 otpauth:// URI(用于扫码)。"""
    return pyotp.totp.TOTP(secret).provisioning_uri(
        name=login_name,
        issuer_name=_TOTP_ISSUER,
    )


def totp_qrcode_png_base64(secret: str, login_name: str) -> str:
    """生成 QR 二维码 PNG, base64 encoded(前端 <img src="data:image/png;base64,..."> 直接用)。"""
    uri = totp_provisioning_uri(secret, login_name)
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def verify_totp(secret: str, code: str) -> bool:
    """校验 6 位 TOTP 验证码,允许 ±30 秒窗口。"""
    if not code or len(code) != 6 or not code.isdigit():
        return False
    return pyotp.TOTP(secret).verify(code, valid_window=1)


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------

def create_access_token(operator_id: int) -> str:
    payload = {
        "sub": str(operator_id),
        "iat": int(datetime.utcnow().timestamp()),
        "exp": int((datetime.utcnow() + timedelta(hours=_JWT_EXPIRE_HOURS)).timestamp()),
    }
    return jwt.encode(payload, _JWT_SECRET, algorithm=_JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[int]:
    """返回 operator_id 或 None(失败)。"""
    try:
        payload = jwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALGORITHM])
        sub = payload.get("sub")
        if sub is None:
            return None
        return int(sub)
    except (JWTError, ValueError):
        return None


# ---------------------------------------------------------------------------
# 客服 CRUD + 登录
# ---------------------------------------------------------------------------


def create_operator(
    session: Session,
    *,
    login_name: str,
    display_name: str,
    password: str,
    remark: Optional[str] = None,
) -> Operator:
    """创建客服。自动生成 TOTP secret(未确认状态)。"""
    if not login_name.strip() or not display_name.strip() or not password.strip():
        raise ValueError("登录名 / 显示名 / 密码不能为空")
    existing = session.scalar(select(Operator).where(Operator.login_name == login_name))
    if existing is not None:
        raise ValueError(f"登录名 {login_name} 已存在")

    operator = Operator(
        login_name=login_name.strip(),
        display_name=display_name.strip(),
        password_hash=hash_password(password),
        totp_secret=generate_totp_secret(),
        totp_confirmed=False,
        is_active=True,
        remark=remark,
    )
    session.add(operator)
    session.flush()
    return operator


def confirm_totp(session: Session, operator: Operator, code: str) -> bool:
    """客服扫码后输入 6 位验证码,验过后置 totp_confirmed=True。"""
    if not verify_totp(operator.totp_secret, code):
        return False
    operator.totp_confirmed = True
    session.flush()
    return True


def login(
    session: Session,
    *,
    login_name: str,
    password: str,
    totp_code: str,
) -> dict:
    """三要素登录,返回 ``{token, operator: {id, login_name, display_name}}``。

    失败抛 AuthError(具体原因不告诉客户端,避免泄密)。
    """
    operator = session.scalar(select(Operator).where(Operator.login_name == login_name))
    if operator is None or not operator.is_active:
        raise AuthError("账号不存在或已停用")
    if not verify_password(password, operator.password_hash):
        raise AuthError("密码错误")
    if not operator.totp_confirmed:
        raise AuthError("二步验证未绑定,请先扫码绑定")
    if not verify_totp(operator.totp_secret, totp_code):
        raise AuthError("二步验证码错误")

    operator.last_login_at = china_now()
    session.flush()
    token = create_access_token(operator.id)
    return {
        "token": token,
        "operator": {
            "id": operator.id,
            "loginName": operator.login_name,
            "displayName": operator.display_name,
        },
    }


def list_operators(session: Session) -> list[Operator]:
    return list(session.scalars(select(Operator).order_by(Operator.id)))


def get_operator(session: Session, operator_id: int) -> Optional[Operator]:
    return session.get(Operator, operator_id)


def deactivate_operator(session: Session, operator: Operator) -> None:
    operator.is_active = False
    session.flush()


def reactivate_operator(session: Session, operator: Operator) -> None:
    operator.is_active = True
    session.flush()
