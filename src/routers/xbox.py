"""XBOX account API routes."""
from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.database import get_db
from src.models.xbox import (
    XboxAccount,
    XboxAccountAuditLog,
    XboxAccountStatus,
    XboxCountry,
    XboxCurrency,
    XboxTransaction,
    XboxTransactionType,
)
from src.services.xbox_account import (
    change_password,
    change_status,
    create_account as service_create_account,
    list_accounts as service_list_accounts,
    list_audit_logs,
    update_account_fields,
)


router = APIRouter(prefix="/xbox", tags=["xbox"])


COUNTRY_CURRENCY = {
    XboxCountry.US: XboxCurrency.USD,
    XboxCountry.UK: XboxCurrency.GBP,
}


def _to_camel(snake: str) -> str:
    head, *tail = snake.split("_")
    return head + "".join(part.title() for part in tail)


class XboxAccountCreate(BaseModel):
    """新增账号请求体（PR #103 升级,加新字段）。"""

    model_config = ConfigDict(populate_by_name=True, alias_generator=_to_camel)

    name: str = Field(..., min_length=1, max_length=120)
    country: XboxCountry
    account_no: Optional[str] = Field(None, max_length=64)
    login_email: Optional[str] = Field(None, max_length=255)
    password: Optional[str] = Field(None, min_length=1)  # 明文,后端加密
    exchange_rate: Optional[Decimal] = None
    status: Optional[XboxAccountStatus] = None
    status_message: Optional[str] = None
    rmb_cost: Optional[Decimal] = None
    local_balance: Optional[Decimal] = None
    remark: Optional[str] = None


class XboxAccountUpdate(BaseModel):
    """编辑账号普通字段（不含 password / status,有专门接口）。

    ``account_no`` 也可在此修改（PR 后续）,会校验唯一性 + 同步 name。
    """

    model_config = ConfigDict(populate_by_name=True, alias_generator=_to_camel)

    name: Optional[str] = Field(None, min_length=1, max_length=120)
    account_no: Optional[str] = Field(None, max_length=64)
    login_email: Optional[str] = Field(None, max_length=255)
    exchange_rate: Optional[Decimal] = None
    rmb_cost: Optional[Decimal] = None
    local_balance: Optional[Decimal] = None
    remark: Optional[str] = None


class XboxAccountPasswordUpdate(BaseModel):
    password: str = Field(..., min_length=1)


class XboxAccountStatusUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=_to_camel)

    status: XboxAccountStatus
    status_message: Optional[str] = None


class XboxAccountOut(BaseModel):
    """账号详情/列表响应（密码不返回明文,只返回 hasPassword 标记）。"""

    model_config = ConfigDict(populate_by_name=True, alias_generator=_to_camel)

    id: int
    name: str
    country: str
    currency: str
    rmb_cost: Decimal
    local_balance: Decimal
    account_no: Optional[str] = None
    login_email: Optional[str] = None
    has_password: bool = False
    exchange_rate: Optional[Decimal] = None
    status: str
    status_message: Optional[str] = None
    last_synced_at: Optional[str] = None
    remark: Optional[str]
    created_at: str


class XboxAccountAuditLogOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=_to_camel)

    id: int
    account_id: int
    action: str
    detail: Optional[str] = None
    operator: Optional[str] = None
    created_at: str


class XboxRechargeRequest(BaseModel):
    rmb_amount: Decimal = Field(..., gt=0)
    local_amount: Decimal = Field(..., gt=0)
    remark: Optional[str] = None


class XboxConsumeRequest(BaseModel):
    local_amount: Decimal = Field(..., gt=0)
    remark: Optional[str] = None


class XboxTransactionOut(BaseModel):
    id: int
    account_id: int
    rmb_amount: Decimal
    local_amount: Decimal
    type: str
    remark: Optional[str]
    created_at: str


class XboxCurrencySummary(BaseModel):
    rmb_cost: Decimal
    local_balance: Decimal


class XboxSummaryOut(BaseModel):
    USD: XboxCurrencySummary
    GBP: XboxCurrencySummary


def _value(value):
    if isinstance(value, Enum):
        return value.value
    return value


def serialize_account(account: XboxAccount) -> XboxAccountOut:
    return XboxAccountOut(
        id=account.id,
        name=account.name,
        country=_value(account.country),
        currency=_value(account.currency),
        rmb_cost=account.rmb_cost,
        local_balance=account.local_balance,
        account_no=account.account_no,
        login_email=account.login_email,
        has_password=bool(account.password_enc),
        exchange_rate=account.exchange_rate,
        status=account.status,
        status_message=account.status_message,
        last_synced_at=account.last_synced_at.isoformat() if account.last_synced_at else None,
        remark=account.remark,
        created_at=account.created_at.isoformat() if account.created_at else "",
    )


def serialize_audit_log(log: XboxAccountAuditLog) -> XboxAccountAuditLogOut:
    return XboxAccountAuditLogOut(
        id=log.id,
        account_id=log.account_id,
        action=log.action,
        detail=log.detail,
        operator=log.operator,
        created_at=log.created_at.isoformat() if log.created_at else "",
    )


def serialize_transaction(transaction: XboxTransaction) -> XboxTransactionOut:
    return XboxTransactionOut(
        id=transaction.id,
        account_id=transaction.account_id,
        rmb_amount=transaction.rmb_amount,
        local_amount=transaction.local_amount,
        type=_value(transaction.type),
        remark=transaction.remark,
        created_at=transaction.created_at.isoformat() if transaction.created_at else "",
    )


def get_account_or_404(session: Session, account_id: int) -> XboxAccount:
    account = session.get(XboxAccount, account_id)
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="XBOX 账号不存在")
    return account


def apply_recharge_to_account(
    session: Session,
    account: XboxAccount,
    rmb_amount: Decimal,
    local_amount: Decimal,
    remark: Optional[str] = None,
) -> XboxTransaction:
    """累加 XBOX 账号 rmb_cost / local_balance 并写入一条 recharge 流水。

    仅 add + flush，不 commit；调用方负责事务边界，便于嵌入更大的原子操作。
    """
    account.rmb_cost = Decimal(account.rmb_cost) + Decimal(rmb_amount)
    account.local_balance = Decimal(account.local_balance) + Decimal(local_amount)
    transaction = XboxTransaction(
        account_id=account.id,
        rmb_amount=Decimal(rmb_amount),
        local_amount=Decimal(local_amount),
        type=XboxTransactionType.RECHARGE.value,
        remark=remark,
    )
    session.add(transaction)
    session.flush()
    return transaction


@router.post(
    "/accounts",
    response_model=XboxAccountOut,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
)
def create_account(request: XboxAccountCreate, db: Session = Depends(get_db)) -> XboxAccountOut:
    """新增账号。可选填账号编号 / 登录邮箱 / 密码（自动加密）/ 汇率 / 状态。"""
    try:
        account = service_create_account(
            db,
            name=request.name,
            country=request.country,
            currency=COUNTRY_CURRENCY[request.country],
            account_no=request.account_no,
            login_email=request.login_email,
            password_plain=request.password,
            exchange_rate=request.exchange_rate,
            status=request.status or XboxAccountStatus.ACTIVE,
            status_message=request.status_message,
            rmb_cost=request.rmb_cost or Decimal("0"),
            local_balance=request.local_balance or Decimal("0"),
            remark=request.remark,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    db.refresh(account)
    return serialize_account(account)


@router.get("/accounts", response_model=list[XboxAccountOut], response_model_by_alias=True)
def list_accounts(
    country: Optional[XboxCountry] = Query(None),
    status_filter: Optional[XboxAccountStatus] = Query(None, alias="status"),
    db: Session = Depends(get_db),
) -> list[XboxAccountOut]:
    accounts = service_list_accounts(
        db,
        status=status_filter.value if status_filter else None,
        country=country.value if country else None,
    )
    return [serialize_account(account) for account in accounts]


@router.patch(
    "/accounts/{account_id}",
    response_model=XboxAccountOut,
    response_model_by_alias=True,
)
def patch_account(
    account_id: int,
    request: XboxAccountUpdate,
    db: Session = Depends(get_db),
) -> XboxAccountOut:
    """更新账号普通字段（不含密码 / 状态）。"""
    account = get_account_or_404(db, account_id)
    try:
        update_account_fields(
            db,
            account,
            name=request.name,
            account_no=request.account_no,
            login_email=request.login_email,
            exchange_rate=request.exchange_rate,
            rmb_cost=request.rmb_cost,
            local_balance=request.local_balance,
            remark=request.remark,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    db.refresh(account)
    return serialize_account(account)


@router.patch(
    "/accounts/{account_id}/password",
    response_model=XboxAccountOut,
    response_model_by_alias=True,
)
def patch_account_password(
    account_id: int,
    request: XboxAccountPasswordUpdate,
    db: Session = Depends(get_db),
) -> XboxAccountOut:
    """单独修改密码（加密存,记审计日志）。"""
    account = get_account_or_404(db, account_id)
    change_password(db, account, request.password)
    db.commit()
    db.refresh(account)
    return serialize_account(account)


@router.patch(
    "/accounts/{account_id}/status",
    response_model=XboxAccountOut,
    response_model_by_alias=True,
)
def patch_account_status(
    account_id: int,
    request: XboxAccountStatusUpdate,
    db: Session = Depends(get_db),
) -> XboxAccountOut:
    """单独修改状态（记审计日志）。"""
    account = get_account_or_404(db, account_id)
    try:
        change_status(db, account, request.status, status_message=request.status_message)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    db.refresh(account)
    return serialize_account(account)


@router.get(
    "/accounts/{account_id}/audit-logs",
    response_model=list[XboxAccountAuditLogOut],
    response_model_by_alias=True,
)
def get_account_audit_logs(
    account_id: int,
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[XboxAccountAuditLogOut]:
    """查账号变更审计日志（最新在前）。"""
    get_account_or_404(db, account_id)
    logs = list_audit_logs(db, account_id, limit=limit)
    return [serialize_audit_log(log) for log in logs]


@router.post(
    "/accounts/{account_id}/recharge",
    response_model=XboxTransactionOut,
    status_code=status.HTTP_201_CREATED,
)
def recharge_account(
    account_id: int,
    request: XboxRechargeRequest,
    db: Session = Depends(get_db),
) -> XboxTransactionOut:
    account = get_account_or_404(db, account_id)
    transaction = apply_recharge_to_account(
        db,
        account,
        rmb_amount=request.rmb_amount,
        local_amount=request.local_amount,
        remark=request.remark,
    )
    db.commit()
    db.refresh(transaction)
    return serialize_transaction(transaction)


@router.post(
    "/accounts/{account_id}/consume",
    response_model=XboxTransactionOut,
    status_code=status.HTTP_201_CREATED,
)
def consume_account(
    account_id: int,
    request: XboxConsumeRequest,
    db: Session = Depends(get_db),
) -> XboxTransactionOut:
    account = get_account_or_404(db, account_id)
    if Decimal(account.local_balance) < request.local_amount:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当地币余额不足")
    account.local_balance = Decimal(account.local_balance) - request.local_amount
    transaction = XboxTransaction(
        account_id=account.id,
        rmb_amount=Decimal("0"),
        local_amount=request.local_amount,
        type=XboxTransactionType.CONSUME.value,
        remark=request.remark,
    )
    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    return serialize_transaction(transaction)


@router.get("/accounts/{account_id}/transactions", response_model=list[XboxTransactionOut])
def list_account_transactions(
    account_id: int,
    db: Session = Depends(get_db),
) -> list[XboxTransactionOut]:
    get_account_or_404(db, account_id)
    transactions = db.scalars(
        select(XboxTransaction)
        .where(XboxTransaction.account_id == account_id)
        .order_by(XboxTransaction.id)
    ).all()
    return [serialize_transaction(transaction) for transaction in transactions]


@router.get("/summary", response_model=XboxSummaryOut)
def xbox_summary(db: Session = Depends(get_db)) -> XboxSummaryOut:
    rows = db.execute(
        select(
            XboxAccount.currency,
            func.coalesce(func.sum(XboxAccount.rmb_cost), 0),
            func.coalesce(func.sum(XboxAccount.local_balance), 0),
        ).group_by(XboxAccount.currency)
    ).all()
    totals = {
        currency: XboxCurrencySummary(
            rmb_cost=Decimal(str(rmb_cost)),
            local_balance=Decimal(str(local_balance)),
        )
        for currency, rmb_cost, local_balance in rows
    }
    empty = XboxCurrencySummary(rmb_cost=Decimal("0"), local_balance=Decimal("0"))
    return XboxSummaryOut(
        USD=totals.get(XboxCurrency.USD.value, empty),
        GBP=totals.get(XboxCurrency.GBP.value, empty),
    )
