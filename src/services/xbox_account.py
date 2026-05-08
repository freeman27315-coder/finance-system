"""XBOX 账号库存服务（PR #103 / issue #102）。

业务能力（CEO 2026-05-08 确认）：
- 新增 / 编辑账号
- 单独修改密码（密文 AES-GCM 存,记审计日志）
- 单独修改状态（记审计日志）
- 列表 + 筛选
- 审计日志查询

密码：AES-256-GCM,密钥从 ``XBOX_ACCOUNT_PASSWORD_KEY`` env 读。
状态枚举：active / disabled / error / need_verification。
"""
from __future__ import annotations

from decimal import Decimal
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.xbox import (
    XboxAccount,
    XboxAccountAuditLog,
    XboxAccountStatus,
    XboxCountry,
    XboxCurrency,
)
from src.utils.crypto import decrypt_password, encrypt_password


def _log(
    session: Session,
    account_id: int,
    action: str,
    detail: Optional[str] = None,
    operator: str = "manual",
) -> XboxAccountAuditLog:
    log = XboxAccountAuditLog(
        account_id=account_id,
        action=action,
        detail=detail,
        operator=operator,
    )
    session.add(log)
    session.flush()
    return log


def create_account(
    session: Session,
    *,
    name: str,
    country: XboxCountry | str,
    currency: XboxCurrency | str,
    account_no: Optional[str] = None,
    login_email: Optional[str] = None,
    password_plain: Optional[str] = None,
    exchange_rate: Optional[Decimal] = None,
    status: XboxAccountStatus | str = XboxAccountStatus.ACTIVE,
    status_message: Optional[str] = None,
    rmb_cost: Decimal = Decimal("0"),
    local_balance: Decimal = Decimal("0"),
    remark: Optional[str] = None,
    operator: str = "manual",
) -> XboxAccount:
    """新增账号 + 自动加密密码 + 写审计日志。"""
    if account_no:
        existing = session.scalar(
            select(XboxAccount).where(XboxAccount.account_no == account_no)
        )
        if existing is not None:
            raise ValueError(f"账号编号 {account_no} 已存在")

    password_enc = encrypt_password(password_plain) if password_plain else None
    status_value = status.value if isinstance(status, XboxAccountStatus) else status
    country_value = country.value if isinstance(country, XboxCountry) else country
    currency_value = currency.value if isinstance(currency, XboxCurrency) else currency

    account = XboxAccount(
        name=name,
        country=country_value,
        currency=currency_value,
        rmb_cost=rmb_cost,
        local_balance=local_balance,
        account_no=account_no,
        login_email=login_email,
        password_enc=password_enc,
        exchange_rate=exchange_rate,
        status=status_value,
        status_message=status_message,
        remark=remark,
    )
    session.add(account)
    session.flush()

    _log(session, account.id, "created", f"name={name}, status={status_value}", operator)
    return account


def update_account_fields(
    session: Session,
    account: XboxAccount,
    *,
    name: Optional[str] = None,
    login_email: Optional[str] = None,
    exchange_rate: Optional[Decimal] = None,
    rmb_cost: Optional[Decimal] = None,
    local_balance: Optional[Decimal] = None,
    remark: Optional[str] = None,
    operator: str = "manual",
) -> XboxAccount:
    """更新非敏感字段（不能在这里改 password / status,有专门接口）。"""
    changes: list[str] = []
    if name is not None and name != account.name:
        changes.append(f"name: {account.name} → {name}")
        account.name = name
    if login_email is not None and login_email != account.login_email:
        changes.append(f"login_email: {account.login_email} → {login_email}")
        account.login_email = login_email
    if exchange_rate is not None and exchange_rate != account.exchange_rate:
        changes.append(f"exchange_rate: {account.exchange_rate} → {exchange_rate}")
        account.exchange_rate = exchange_rate
    if rmb_cost is not None and rmb_cost != account.rmb_cost:
        changes.append(f"rmb_cost: {account.rmb_cost} → {rmb_cost}")
        account.rmb_cost = rmb_cost
    if local_balance is not None and local_balance != account.local_balance:
        changes.append(f"local_balance: {account.local_balance} → {local_balance}")
        account.local_balance = local_balance
    if remark is not None and remark != account.remark:
        changes.append("remark changed")
        account.remark = remark

    if changes:
        _log(session, account.id, "updated", "; ".join(changes), operator)
    session.flush()
    return account


def change_password(
    session: Session,
    account: XboxAccount,
    new_password: str,
    operator: str = "manual",
) -> XboxAccount:
    """单独修改密码（加密存 + 写审计）。"""
    if not new_password:
        raise ValueError("新密码不能为空")
    account.password_enc = encrypt_password(new_password)
    _log(session, account.id, "password_changed", "password_changed", operator)
    session.flush()
    return account


def change_status(
    session: Session,
    account: XboxAccount,
    new_status: XboxAccountStatus | str,
    status_message: Optional[str] = None,
    operator: str = "manual",
) -> XboxAccount:
    """单独修改状态（写审计）。"""
    new_value = new_status.value if isinstance(new_status, XboxAccountStatus) else new_status
    if new_value not in {s.value for s in XboxAccountStatus}:
        raise ValueError(f"非法状态: {new_value}")
    if account.status == new_value and account.status_message == status_message:
        return account
    detail = f"status: {account.status} → {new_value}"
    if status_message:
        detail += f" ({status_message})"
    account.status = new_value
    account.status_message = status_message
    _log(session, account.id, "status_changed", detail, operator)
    session.flush()
    return account


def list_accounts(
    session: Session,
    *,
    status: Optional[str] = None,
    country: Optional[str] = None,
) -> list[XboxAccount]:
    """列表 + 状态/国家筛选。"""
    stmt = select(XboxAccount).order_by(XboxAccount.id.desc())
    if status:
        stmt = stmt.where(XboxAccount.status == status)
    if country:
        stmt = stmt.where(XboxAccount.country == country)
    return list(session.scalars(stmt))


def list_audit_logs(
    session: Session,
    account_id: int,
    limit: int = 50,
) -> list[XboxAccountAuditLog]:
    return list(
        session.scalars(
            select(XboxAccountAuditLog)
            .where(XboxAccountAuditLog.account_id == account_id)
            .order_by(XboxAccountAuditLog.id.desc())
            .limit(limit)
        )
    )


def reveal_password(account: XboxAccount) -> str:
    """解密返回明文密码（仅业务必要时调用,如 Microsoft 登录）。"""
    if not account.password_enc:
        raise ValueError("该账号未设置密码")
    return decrypt_password(account.password_enc)
