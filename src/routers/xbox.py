"""XBOX account API routes."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
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
    XboxOrder,
    XboxOrderStatus,
    XboxSaleRecord,
    XboxTransaction,
    XboxTransactionType,
    XboxWalletItem,
    XboxWalletMethod,
)
from src.services.xbox_account import (
    change_password,
    change_status,
    create_account as service_create_account,
    list_accounts as service_list_accounts,
    list_audit_logs,
    update_account_fields,
)
from src.services.xbox_order import (
    create_order as service_create_order,
    get_order_or_404,
    list_orders as service_list_orders,
    update_order_completion,
)
from src.services.xbox_sale import (
    list_sale_records,
    update_sale_record_fields,
)
from src.services.xbox_wallet_setting import (
    list_wallet_methods,
    upsert_wallet_settings,
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


# ==================================================================
# PR #110 P0.2 — 订单 / 销售记录 / 钱包设置 端点
# ==================================================================


# ----- Schemas -----
class XboxOrderCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=_to_camel)

    account_id: int
    order_no: str = Field(..., min_length=1, max_length=64)
    amount_local: Decimal
    currency_local: str = Field(..., min_length=1, max_length=8)
    order_at: datetime
    exchange_rate: Optional[Decimal] = None


class XboxOrderCompletion(BaseModel):
    """订单补齐字段。全部填齐后自动转销售记录。"""

    model_config = ConfigDict(populate_by_name=True, alias_generator=_to_camel)

    sale_date: Optional[date] = None
    product_name: Optional[str] = Field(None, min_length=1, max_length=255)
    operator_name: Optional[str] = Field(None, min_length=1, max_length=64)
    sale_price: Optional[Decimal] = None
    sale_currency: Optional[str] = None
    wallet_method_id: Optional[int] = None
    wallet_item_id: Optional[int] = None


class XboxOrderOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=_to_camel)

    id: int
    account_id: int
    order_no: str
    amount_local: Decimal
    currency_local: str
    exchange_rate: Optional[Decimal] = None
    rmb_cost: Decimal
    order_at: str
    status: str
    sale_date: Optional[str] = None
    product_name: Optional[str] = None
    operator_name: Optional[str] = None
    sale_price: Optional[Decimal] = None
    sale_currency: Optional[str] = None
    wallet_method_id: Optional[int] = None
    wallet_item_id: Optional[int] = None
    sale_record_id: Optional[int] = None
    created_at: str
    last_updated_at: str


class XboxSaleRecordOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=_to_camel)

    id: int
    account_id: int
    sale_date: str
    product_name: str
    operator_name: str
    sale_price: Decimal
    sale_currency: str
    wallet_method_id: int
    wallet_item_id: int
    wallet_item_label: str
    wallet_pool_id: int
    bookkeeping_tx_id: Optional[int] = None
    order_ids: list[int] = Field(default_factory=list)
    created_at: str
    last_updated_at: str


class XboxSaleRecordUpdate(BaseModel):
    """改销售记录字段。后端自动联动钱包余额。"""

    model_config = ConfigDict(populate_by_name=True, alias_generator=_to_camel)

    sale_date: Optional[date] = None
    product_name: Optional[str] = None
    operator_name: Optional[str] = None
    sale_price: Optional[Decimal] = None
    sale_currency: Optional[str] = None
    wallet_method_id: Optional[int] = None
    wallet_item_id: Optional[int] = None
    wallet_item_label: Optional[str] = None
    wallet_pool_id: Optional[int] = None


class XboxWalletItemOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=_to_camel)

    id: int
    code: str
    label: str
    wallet_pool_id: int
    is_active: bool


class XboxWalletMethodOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=_to_camel)

    id: int
    code: str
    label: str
    is_active: bool
    items: list[XboxWalletItemOut]


# ----- Serializers -----
def serialize_order(order: XboxOrder) -> XboxOrderOut:
    return XboxOrderOut(
        id=order.id,
        account_id=order.account_id,
        order_no=order.order_no,
        amount_local=order.amount_local,
        currency_local=order.currency_local,
        exchange_rate=order.exchange_rate,
        rmb_cost=order.rmb_cost,
        order_at=order.order_at.isoformat() if order.order_at else "",
        status=order.status,
        sale_date=order.sale_date.isoformat() if order.sale_date else None,
        product_name=order.product_name,
        operator_name=order.operator_name,
        sale_price=order.sale_price,
        sale_currency=order.sale_currency,
        wallet_method_id=order.wallet_method_id,
        wallet_item_id=order.wallet_item_id,
        sale_record_id=order.sale_record_id,
        created_at=order.created_at.isoformat() if order.created_at else "",
        last_updated_at=order.last_updated_at.isoformat() if order.last_updated_at else "",
    )


def serialize_sale_record(record: XboxSaleRecord, order_ids: list[int]) -> XboxSaleRecordOut:
    return XboxSaleRecordOut(
        id=record.id,
        account_id=record.account_id,
        sale_date=record.sale_date.isoformat() if record.sale_date else "",
        product_name=record.product_name,
        operator_name=record.operator_name,
        sale_price=record.sale_price,
        sale_currency=record.sale_currency,
        wallet_method_id=record.wallet_method_id,
        wallet_item_id=record.wallet_item_id,
        wallet_item_label=record.wallet_item_label,
        wallet_pool_id=record.wallet_pool_id,
        bookkeeping_tx_id=record.bookkeeping_tx_id,
        order_ids=order_ids,
        created_at=record.created_at.isoformat() if record.created_at else "",
        last_updated_at=record.last_updated_at.isoformat() if record.last_updated_at else "",
    )


def serialize_method(method: XboxWalletMethod) -> XboxWalletMethodOut:
    items = sorted(method.items, key=lambda i: i.id)
    return XboxWalletMethodOut(
        id=method.id,
        code=method.code,
        label=method.label,
        is_active=method.is_active,
        items=[
            XboxWalletItemOut(
                id=it.id,
                code=it.code,
                label=it.label,
                wallet_pool_id=it.wallet_pool_id,
                is_active=it.is_active,
            )
            for it in items
        ],
    )


# ----- Order endpoints -----
@router.post(
    "/orders",
    response_model=XboxOrderOut,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
)
def create_order_endpoint(request: XboxOrderCreate, db: Session = Depends(get_db)) -> XboxOrderOut:
    """手动建订单（P0.2 阶段,P2 改为 Microsoft 自动同步）。"""
    account = get_account_or_404(db, request.account_id)
    try:
        order = service_create_order(
            db,
            account=account,
            order_no=request.order_no,
            amount_local=request.amount_local,
            currency_local=request.currency_local,
            order_at=request.order_at,
            exchange_rate=request.exchange_rate,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    db.refresh(order)
    return serialize_order(order)


@router.get(
    "/orders",
    response_model=list[XboxOrderOut],
    response_model_by_alias=True,
)
def list_orders_endpoint(
    account_id: Optional[int] = Query(None, alias="accountId"),
    status_filter: Optional[XboxOrderStatus] = Query(None, alias="status"),
    db: Session = Depends(get_db),
) -> list[XboxOrderOut]:
    orders = service_list_orders(
        db,
        account_id=account_id,
        status=status_filter.value if status_filter else None,
    )
    return [serialize_order(o) for o in orders]


@router.patch(
    "/orders/{order_id}",
    response_model=XboxOrderOut,
    response_model_by_alias=True,
)
def patch_order_endpoint(
    order_id: int,
    request: XboxOrderCompletion,
    db: Session = Depends(get_db),
) -> XboxOrderOut:
    """补齐订单字段。全部填齐自动转销售（CEO Q3A）。"""
    order = get_order_or_404(db, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="订单不存在")
    try:
        update_order_completion(
            db,
            order,
            sale_date=request.sale_date,
            product_name=request.product_name,
            operator_name=request.operator_name,
            sale_price=request.sale_price,
            sale_currency=request.sale_currency,
            wallet_method_id=request.wallet_method_id,
            wallet_item_id=request.wallet_item_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    db.refresh(order)
    return serialize_order(order)


# ----- Sale record endpoints -----
@router.get(
    "/sale-records",
    response_model=list[XboxSaleRecordOut],
    response_model_by_alias=True,
)
def list_sale_records_endpoint(
    account_id: Optional[int] = Query(None, alias="accountId"),
    wallet_pool_id: Optional[int] = Query(None, alias="walletPoolId"),
    db: Session = Depends(get_db),
) -> list[XboxSaleRecordOut]:
    records = list_sale_records(db, account_id=account_id, wallet_pool_id=wallet_pool_id)
    out: list[XboxSaleRecordOut] = []
    for record in records:
        order_ids = [
            o.id
            for o in db.scalars(
                select(XboxOrder).where(XboxOrder.sale_record_id == record.id)
            )
        ]
        out.append(serialize_sale_record(record, order_ids))
    return out


@router.patch(
    "/sale-records/{record_id}",
    response_model=XboxSaleRecordOut,
    response_model_by_alias=True,
)
def patch_sale_record_endpoint(
    record_id: int,
    request: XboxSaleRecordUpdate,
    db: Session = Depends(get_db),
) -> XboxSaleRecordOut:
    """改销售记录字段（自动联动钱包余额, CEO Q2A + Q3A）。"""
    record = db.get(XboxSaleRecord, record_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="销售记录不存在")
    try:
        update_sale_record_fields(
            db,
            record,
            sale_date=request.sale_date,
            product_name=request.product_name,
            operator_name=request.operator_name,
            sale_price=request.sale_price,
            sale_currency=request.sale_currency,
            wallet_method_id=request.wallet_method_id,
            wallet_item_id=request.wallet_item_id,
            wallet_item_label=request.wallet_item_label,
            wallet_pool_id=request.wallet_pool_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    db.refresh(record)
    order_ids = [
        o.id
        for o in db.scalars(select(XboxOrder).where(XboxOrder.sale_record_id == record.id))
    ]
    return serialize_sale_record(record, order_ids)


# ----- Wallet settings endpoints -----
@router.put(
    "/wallet-settings",
    response_model=dict,
)
def upsert_wallet_settings_endpoint(
    payload: list[dict] = Body(...),
    db: Session = Depends(get_db),
) -> dict:
    """财务系统推送钱包设置（IF-02）。

    Body 是 method 列表。每条 method 含 code/label/items[]。
    item 含 code/label/walletPoolId/isActive。
    """
    try:
        result = upsert_wallet_settings(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    return result


@router.get(
    "/wallet-settings",
    response_model=list[XboxWalletMethodOut],
    response_model_by_alias=True,
)
def list_wallet_settings_endpoint(
    only_active: bool = Query(True, alias="onlyActive"),
    db: Session = Depends(get_db),
) -> list[XboxWalletMethodOut]:
    methods = list_wallet_methods(db, only_active=only_active)
    return [serialize_method(m) for m in methods]


# ----- 资金池可选钱包列表（CEO 2026-05-08 Q1A：全部钱包大类都能当资金池）-----


class XboxPoolOptionWallet(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=_to_camel)

    id: int
    name: str
    currency: str
    full_path: str  # 含父级路径,如 "支付宝钱包 / 丙火网络支付宝"


class XboxPoolOptionGroup(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=_to_camel)

    group_code: str  # ASSET_RMB / ASSET_USDT / ASSET_USD / TAOBAO / TAIWAN / VENDOR / XBOX
    group_label: str
    wallets: list[XboxPoolOptionWallet]


# 钱包大类显示标签 + 顺序
_GROUP_META: list[tuple[str, str]] = [
    ("ASSET_RMB", "资产 RMB"),
    ("ASSET_USDT", "资产 USDT"),
    ("ASSET_USD", "资产 USD"),
    ("TAOBAO", "淘宝"),
    ("TAIWAN", "台湾"),
    ("VENDOR", "供应商"),
    ("XBOX", "XBOX"),
]


@router.get(
    "/wallet-pool-options",
    response_model=list[XboxPoolOptionGroup],
    response_model_by_alias=True,
)
def list_wallet_pool_options(db: Session = Depends(get_db)) -> list[XboxPoolOptionGroup]:
    """返回所有可作"资金池"的钱包,按大类分组（CEO Q1A：全部钱包大类都行）。

    校验规则: 销售记录创建/修改时,sale_currency 必须等于钱包 currency,
    所以前端可在所有大类下挑,后端会按币种校验拒绝不匹配的组合。
    """
    from src.models.wallet import Wallet  # 局部 import 避免循环依赖问题

    # 取所有非 group + 未删除的叶子钱包
    wallets = list(
        db.scalars(
            select(Wallet)
            .where(Wallet.is_group.is_(False), Wallet.deleted_at.is_(None))
            .order_by(Wallet.id)
        )
    )

    # 计算每个钱包的"完整路径"(从根到自己)
    by_id = {w.id: w for w in db.scalars(select(Wallet))}

    def full_path(w: Wallet) -> str:
        parts: list[str] = []
        cur: Wallet | None = w
        while cur is not None:
            parts.append(cur.name)
            cur = by_id.get(cur.parent_id) if cur.parent_id is not None else None
        return " / ".join(reversed(parts))

    # 按 type 分组
    by_type: dict[str, list[Wallet]] = {}
    for w in wallets:
        type_value = w.type.value if hasattr(w.type, "value") else str(w.type)
        by_type.setdefault(type_value, []).append(w)

    out: list[XboxPoolOptionGroup] = []
    for type_code, label in _GROUP_META:
        items = by_type.get(type_code, [])
        if not items:
            continue
        out.append(
            XboxPoolOptionGroup(
                group_code=type_code,
                group_label=label,
                wallets=[
                    XboxPoolOptionWallet(
                        id=w.id,
                        name=w.name,
                        currency=w.currency.value if hasattr(w.currency, "value") else str(w.currency),
                        full_path=full_path(w),
                    )
                    for w in items
                ],
            )
        )
    return out
