"""XBOX account API routes."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.database import get_db
from src.models.xbox import (
    XboxAccount,
    XboxAccountAuditLog,
    XboxAccountStatus,
    XboxBalanceSnapshot,
    XboxChangeLog,
    XboxCountry,
    XboxCurrency,
    XboxOrder,
    XboxOrderStatus,
    XboxReconcileMapping,
    XboxSaleRecord,
    XboxSyncBatch,
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
    move_order_to_different_sale_record,
    update_order_completion,
)
from src.services.xbox_sale import (
    get_sales_summary,
    list_sale_records,
    update_sale_record_fields,
)
from src.services.xbox_reconcile import (
    create_mapping,
    delete_mapping,
    get_reconcile_report_for_day,
    list_mappings,
)
from src.services.xbox_sync import (
    VALID_SYNC_COUNTS,
    list_balance_snapshots,
    list_sync_batches,
    refresh_account_balance,
    trigger_sync,
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


# CEO 2026-05-17: 国家 → 默认货币的反向映射, 从 _CURRENCY_TO_COUNTRY 自动派生。
# 创建账号时, 如果用户传了 country 但没传 currency, 用这表填默认。
def _default_currency_for_country(country_code: str) -> str:
    """US → USD, UK → GBP, EU → EUR, JP → JPY, 等。未知国家 → USD。"""
    from src.services.xbox_sync import _CURRENCY_TO_COUNTRY
    for cur_key, (country_val, currency_val) in _CURRENCY_TO_COUNTRY.items():
        if country_val == country_code:
            return currency_val
    # 兜底: ISO 3166 国家码 + "D" 之类的猜测, 或直接 USD
    return "USD"


def _to_camel(snake: str) -> str:
    head, *tail = snake.split("_")
    return head + "".join(part.title() for part in tail)


class XboxAccountCreate(BaseModel):
    """新增账号请求体（PR #103 升级,加新字段）。

    CEO 2026-05-12 Q1-A: country 字段不再必填,默认占位 US,
    第一次同步成功后根据爬到的 currency 自动识别(USD→US, GBP→UK)。
    """

    model_config = ConfigDict(populate_by_name=True, alias_generator=_to_camel)

    name: str = Field(..., min_length=1, max_length=120)
    # CEO 2026-05-17: 不限制必须是 US/UK, 可以传任何国家码
    country: Optional[str] = Field(None, max_length=8)
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
    is_available_for_claim: bool = False  # CEO 2026-05-11
    country_identified: bool = False  # CEO 2026-05-12 Q1-A: 国家是否已自动识别
    remark: Optional[str]
    created_at: str


class XboxAccountAvailabilityUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=_to_camel)

    is_available_for_claim: bool


class XboxAccountAuditLogOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=_to_camel)

    id: int
    account_id: int
    action: str
    detail: Optional[str] = None
    operator: Optional[str] = None
    created_at: str



class XboxCurrencySummary(BaseModel):
    rmb_cost: Decimal
    local_balance: Decimal
    # CEO 2026-05-17: 加 accountCount 让前端不用再 GET 整张账号表算数量
    account_count: int = 0

    model_config = ConfigDict(populate_by_name=True, alias_generator=_to_camel)


# CEO 2026-05-17: XboxSummaryOut 从写死的 {USD, GBP} 改成动态 {币种: summary}。
# 这样不论新加什么币种(EUR/JPY/CNY/HKD...), 前端都自动能看到对应汇总卡片。
# 后端不再过滤, 把所有币种的汇总都吐出来。


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
        is_available_for_claim=bool(account.is_available_for_claim),
        country_identified=bool(account.country_identified),
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



def get_account_or_404(session: Session, account_id: int) -> XboxAccount:
    account = session.get(XboxAccount, account_id)
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="XBOX 账号不存在")
    return account



@router.post(
    "/accounts",
    response_model=XboxAccountOut,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
)
def create_account(request: XboxAccountCreate, db: Session = Depends(get_db)) -> XboxAccountOut:
    """新增账号。可选填账号编号 / 登录邮箱 / 密码（自动加密）/ 汇率 / 状态。

    CEO 2026-05-12 Q1-A: country 字段不再必填。不传时占位 US,country_identified=False;
    首次同步后根据爬到的 currency 自动识别(USD→US, GBP→UK)。
    """
    # 国家占位: 未传时默认 US/USD,country_identified=False 标记为"待识别"
    # CEO 2026-05-17: country 可以是任意字符串 (US/UK/JP/EU/...), 自动派生默认货币
    effective_country = request.country or "US"
    effective_currency = _default_currency_for_country(effective_country)
    try:
        account = service_create_account(
            db,
            name=request.name,
            country=effective_country,
            currency=effective_currency,
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
        # 如果 CEO 明确传了 country, 视为已确认(skip auto-detect);否则待识别
        if request.country is not None:
            account.country_identified = True
            db.flush()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    db.refresh(account)
    return serialize_account(account)


@router.get("/accounts", response_model=list[XboxAccountOut], response_model_by_alias=True)
def list_accounts(
    # CEO 2026-05-17: country 不再枚举锁死, 接受任意字符串(US/UK/JP/EU 等)
    country: Optional[str] = Query(None, max_length=8),
    status_filter: Optional[XboxAccountStatus] = Query(None, alias="status"),
    db: Session = Depends(get_db),
) -> list[XboxAccountOut]:
    accounts = service_list_accounts(
        db,
        status=status_filter.value if status_filter else None,
        country=country,
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


@router.patch(
    "/accounts/{account_id}/availability",
    response_model=XboxAccountOut,
    response_model_by_alias=True,
)
def patch_account_availability(
    account_id: int,
    request: XboxAccountAvailabilityUpdate,
    db: Session = Depends(get_db),
) -> XboxAccountOut:
    """CEO 后台: 标记账号是否"可出库"（客服可领取的开关）。"""
    account = get_account_or_404(db, account_id)
    account.is_available_for_claim = bool(request.is_available_for_claim)
    db.add(
        XboxAccountAuditLog(
            account_id=account.id,
            action="updated",
            detail=f"is_available_for_claim → {request.is_available_for_claim}",
            operator="admin",
        )
    )
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




@router.get("/summary")
def xbox_summary(db: Session = Depends(get_db)) -> dict[str, XboxCurrencySummary]:
    """按币种聚合所有账号的 RMB 成本 + 本币余额 + 账号数。
    CEO 2026-05-17: 返回所有币种(不止 USD/GBP), 前端按响应里的 key 动态渲染。
    CEO 2026-05-17 v2: 成本算式改为 SUM(local_balance × exchange_rate),
    汇率为空/0 的账号那行成本算 0(还是包含在账号数里), 不再读老的 rmb_cost 字段。
    """
    # 用 COALESCE 把 NULL 汇率视作 0
    rmb_cost_expr = func.coalesce(
        func.sum(XboxAccount.local_balance * func.coalesce(XboxAccount.exchange_rate, 0)),
        0,
    )
    rows = db.execute(
        select(
            XboxAccount.currency,
            rmb_cost_expr,
            func.coalesce(func.sum(XboxAccount.local_balance), 0),
            func.count(XboxAccount.id),
        ).group_by(XboxAccount.currency)
    ).all()
    return {
        (currency or "UNKNOWN"): XboxCurrencySummary(
            rmb_cost=Decimal(str(rmb_cost)),
            local_balance=Decimal(str(local_balance)),
            account_count=int(count_),
        )
        for currency, rmb_cost, local_balance, count_ in rows
    }


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
    """订单补齐字段。全部填齐后自动转销售记录。

    CEO 2026-05-12: 销售日期(sale_date)系统自动填(= 订单时间, 中国时区精确到秒),
    客服无需传; 传了也会接受(datetime 字符串, ISO 8601)。
    """

    model_config = ConfigDict(populate_by_name=True, alias_generator=_to_camel)

    sale_date: Optional[datetime] = None
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
    """改销售记录字段。后端自动联动钱包余额。

    CEO 2026-05-12: sale_date 是 datetime(中国时区精确到秒), CEO 后台可改。
    """

    model_config = ConfigDict(populate_by_name=True, alias_generator=_to_camel)

    sale_date: Optional[datetime] = None
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
    # CEO 2026-05-14: 该方式下所有 item 对应 wallet 的币种统一(业务约定)。
    # 客服补销售时选完方式自动锁定币种,无需手填。
    # 取第一个 item 的 wallet_pool.currency; items 为空时 None。
    currency: Optional[str] = None


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


def serialize_method(
    method: XboxWalletMethod,
    currency_map: Optional[dict[int, str]] = None,
    only_active_items: bool = False,
) -> XboxWalletMethodOut:
    # CEO 2026-05-14: only_active_items=True 时, 过滤被软删除(is_active=False) 的
    # 备注模板, 避免编辑钱包设置页删了之后还看见。
    raw_items = sorted(method.items, key=lambda i: i.id)
    items = (
        [it for it in raw_items if it.is_active] if only_active_items else raw_items
    )
    # 推导 method 币种 = 第一个 item 的 wallet currency
    method_currency: Optional[str] = None
    if currency_map and items:
        method_currency = currency_map.get(items[0].wallet_pool_id)
    return XboxWalletMethodOut(
        id=method.id,
        code=method.code,
        label=method.label,
        is_active=method.is_active,
        currency=method_currency,
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
    from_date: Optional[date] = Query(None, alias="from"),
    to_date: Optional[date] = Query(None, alias="to"),
    db: Session = Depends(get_db),
) -> list[XboxOrderOut]:
    orders = service_list_orders(
        db,
        account_id=account_id,
        status=status_filter.value if status_filter else None,
        from_date=from_date,
        to_date=to_date,
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
    """补齐订单字段。

    - 待补齐订单（status=pending_complete）: 字段填齐自动转销售
    - 已转销售订单（status=converted）: 改 wallet_method_id / wallet_item_id 触发"拆单"
      老销售记录金额扣减,新销售记录金额累加(或新建),钱包余额联动。
    """
    order = get_order_or_404(db, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="订单不存在")

    try:
        # 已转销售 + 改 wallet_item_id → 拆单
        if (
            order.status == XboxOrderStatus.CONVERTED.value
            and request.wallet_item_id is not None
            and request.wallet_item_id != order.wallet_item_id
        ):
            new_method_id = request.wallet_method_id or order.wallet_method_id
            move_order_to_different_sale_record(
                db, order, new_method_id, request.wallet_item_id
            )
        else:
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
    from_date: Optional[date] = Query(None, alias="from"),
    to_date: Optional[date] = Query(None, alias="to"),
    db: Session = Depends(get_db),
) -> list[XboxSaleRecordOut]:
    records = list_sale_records(
        db,
        account_id=account_id,
        wallet_pool_id=wallet_pool_id,
        from_date=from_date,
        to_date=to_date,
    )
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
    from src.models.wallet import Wallet  # 局部 import 避免循环

    methods = list_wallet_methods(db, only_active=only_active)
    # CEO 2026-05-14: 预加载所有 item 对应钱包的币种, 注入 method.currency
    # 同时把 only_active 透传给 serialize_method, 一并过滤掉软删除的备注模板
    # (避免 CEO 在编辑钱包设置页删了之后刷新还看见)。
    wallet_ids = {it.wallet_pool_id for m in methods for it in m.items if it.is_active or not only_active}
    currency_map: dict[int, str] = {}
    if wallet_ids:
        wallets = db.scalars(select(Wallet).where(Wallet.id.in_(wallet_ids))).all()
        for w in wallets:
            cur = w.currency.value if hasattr(w.currency, "value") else w.currency
            currency_map[w.id] = cur
    return [
        serialize_method(m, currency_map, only_active_items=only_active)
        for m in methods
    ]


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


# 钱包大类显示标签 + 顺序（XBOX 钱包设置只用 XBOX_SALES_LEDGER,
# 但接口保留全部大类返回供其他业务复用）
_GROUP_META: list[tuple[str, str]] = [
    ("XBOX_SALES_LEDGER", "XBOX 销售归口"),  # 默认放最前,XBOX 钱包设置首选
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
def list_wallet_pool_options(
    xbox_only: bool = Query(True, alias="xboxOnly"),
    include_groups: bool = Query(False, alias="includeGroups"),
    db: Session = Depends(get_db),
) -> list[XboxPoolOptionGroup]:
    """返回可作"资金池"的钱包,按大类分组。

    CEO 2026-05-08 Q2:A - 默认 ``xboxOnly=true``,只返回 XBOX 销售归口理论值钱包,
    防止客服误选实际值钱包。前端可显式传 ``?xboxOnly=false`` 取全部钱包(高级模式)。

    ``includeGroups`` (默认 false):
    - true 时也返回 group 钱包(用于对账映射,允许选店铺总钱包)
    - false 时只返回叶子钱包(给销售记录资金池下拉用,group 不能存余额)

    校验规则: 销售记录创建/修改时, sale_currency 必须等于钱包 currency,
    后端按币种校验拒绝不匹配的组合。
    """
    from src.models.wallet import Wallet  # 局部 import 避免循环依赖问题

    # 取所有未删除的钱包
    stmt = select(Wallet).where(Wallet.deleted_at.is_(None))
    if not include_groups:
        stmt = stmt.where(Wallet.is_group.is_(False))
    wallets = list(db.scalars(stmt.order_by(Wallet.id)))

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
        # xbox_only 模式只返回 XBOX_SALES_LEDGER 大类
        if xbox_only and type_code != "XBOX_SALES_LEDGER":
            continue
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


# ----- 订单 / 销售记录变更日志（CEO Q3:A）-----


class XboxChangeLogOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=_to_camel)

    id: int
    entity_type: str
    entity_id: int
    action: str
    detail: Optional[str] = None
    operator: Optional[str] = None
    created_at: str


def _serialize_change_log(log: XboxChangeLog) -> XboxChangeLogOut:
    return XboxChangeLogOut(
        id=log.id,
        entity_type=log.entity_type,
        entity_id=log.entity_id,
        action=log.action,
        detail=log.detail,
        operator=log.operator,
        created_at=log.created_at.isoformat() if log.created_at else "",
    )


@router.get(
    "/sales-summary",
    response_model=dict,
)
def sales_summary_endpoint(
    from_date: Optional[date] = Query(None, alias="from"),
    to_date: Optional[date] = Query(None, alias="to"),
    db: Session = Depends(get_db),
) -> dict:
    """销售汇总: 按币种 / 收款方式 / 备注模板。"""
    return get_sales_summary(db, from_date=from_date, to_date=to_date)


@router.get(
    "/sale-records/export",
    response_class=Response,
)
def export_sale_records_endpoint(
    from_date: Optional[date] = Query(None, alias="from"),
    to_date: Optional[date] = Query(None, alias="to"),
    account_id: Optional[int] = Query(None, alias="accountId"),
    db: Session = Depends(get_db),
) -> Response:
    """导出销售记录为 Excel。字段：日期/账号编号/商品/经办人/售价/币种/收款方式/备注模板/资金池钱包名/关联订单号。"""
    from io import BytesIO
    from openpyxl import Workbook
    from src.models.wallet import Wallet

    records = list_sale_records(
        db, account_id=account_id, from_date=from_date, to_date=to_date
    )
    # 预加载账号 + method + 钱包名
    account_map = {a.id: a for a in db.scalars(select(XboxAccount))}
    method_map = {m.id: m for m in db.scalars(select(XboxWalletMethod))}
    wallet_map = {w.id: w for w in db.scalars(select(Wallet))}

    wb = Workbook()
    ws = wb.active
    ws.title = "XBOX 销售记录"
    headers = [
        "销售日期", "账号编号", "商品", "经办人", "售价", "币种",
        "收款方式", "备注模板", "资金池钱包", "关联订单号",
    ]
    ws.append(headers)
    for record in records:
        account = account_map.get(record.account_id)
        method = method_map.get(record.wallet_method_id)
        wallet = wallet_map.get(record.wallet_pool_id)
        order_ids = [
            o.order_no
            for o in db.scalars(select(XboxOrder).where(XboxOrder.sale_record_id == record.id))
        ]
        ws.append([
            str(record.sale_date) if record.sale_date else "",
            account.account_no or account.name if account else "",
            record.product_name or "",
            record.operator_name or "",
            float(record.sale_price),
            record.sale_currency or "",
            method.label if method else "",
            record.wallet_item_label or "",
            wallet.name if wallet else "",
            ", ".join(order_ids),
        ])

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    filename = f"xbox-sale-records-{from_date or 'all'}-{to_date or 'all'}.xlsx"
    return Response(
        content=buf.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get(
    "/orders/{order_id}/change-logs",
    response_model=list[XboxChangeLogOut],
    response_model_by_alias=True,
)
def get_order_change_logs(
    order_id: int,
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[XboxChangeLogOut]:
    """查订单变更历史。"""
    logs = list(
        db.scalars(
            select(XboxChangeLog)
            .where(XboxChangeLog.entity_type == "order", XboxChangeLog.entity_id == order_id)
            .order_by(XboxChangeLog.id.desc())
            .limit(limit)
        )
    )
    return [_serialize_change_log(log) for log in logs]


@router.get(
    "/sale-records/{record_id}/change-logs",
    response_model=list[XboxChangeLogOut],
    response_model_by_alias=True,
)
def get_sale_record_change_logs(
    record_id: int,
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[XboxChangeLogOut]:
    """查销售记录变更历史（含创建/合单/改售价/改资金池）。"""
    logs = list(
        db.scalars(
            select(XboxChangeLog)
            .where(XboxChangeLog.entity_type == "sale_record", XboxChangeLog.entity_id == record_id)
            .order_by(XboxChangeLog.id.desc())
            .limit(limit)
        )
    )
    return [_serialize_change_log(log) for log in logs]


# ----- 对账（CEO 2026-05-08 Q1A+Q2A+Q3A+Q4A）-----


class XboxReconcileMappingOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=_to_camel)

    id: int
    theoretical_wallet_id: int
    actual_wallet_id: int
    created_at: str


class XboxReconcileMappingCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=_to_camel)

    theoretical_wallet_id: int
    actual_wallet_id: int


def _serialize_mapping(m: XboxReconcileMapping) -> XboxReconcileMappingOut:
    return XboxReconcileMappingOut(
        id=m.id,
        theoretical_wallet_id=m.theoretical_wallet_id,
        actual_wallet_id=m.actual_wallet_id,
        created_at=m.created_at.isoformat() if m.created_at else "",
    )


@router.get(
    "/reconcile-mappings",
    response_model=list[XboxReconcileMappingOut],
    response_model_by_alias=True,
)
def list_reconcile_mappings_endpoint(db: Session = Depends(get_db)) -> list[XboxReconcileMappingOut]:
    return [_serialize_mapping(m) for m in list_mappings(db)]


@router.post(
    "/reconcile-mappings",
    response_model=XboxReconcileMappingOut,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
)
def create_reconcile_mapping_endpoint(
    request: XboxReconcileMappingCreate,
    db: Session = Depends(get_db),
) -> XboxReconcileMappingOut:
    try:
        mapping = create_mapping(
            db,
            theoretical_wallet_id=request.theoretical_wallet_id,
            actual_wallet_id=request.actual_wallet_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    db.refresh(mapping)
    return _serialize_mapping(mapping)


@router.delete(
    "/reconcile-mappings/{mapping_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_reconcile_mapping_endpoint(
    mapping_id: int,
    db: Session = Depends(get_db),
) -> Response:
    ok = delete_mapping(db, mapping_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="映射不存在")
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/reconcile",
    response_model=list[dict],
)
def reconcile_report_endpoint(
    target_date: date = Query(..., alias="date"),
    db: Session = Depends(get_db),
) -> list[dict]:
    """对账报告：每个理论值钱包当天的理论金额 vs 实际金额合计 vs 差异。"""
    return get_reconcile_report_for_day(db, target_date)


# ===================================================================
# Microsoft 订单同步（FR-04 / IF-03,阶段 1 mock）
# ===================================================================


class XboxSyncRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=_to_camel)

    account_id: int
    count: int = 20  # 10/20/30/50


class XboxSyncBatchOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=_to_camel)

    id: int
    account_id: int
    started_at: str
    finished_at: Optional[str] = None
    requested_count: int
    fetched_count: int
    success: bool
    failure_category: Optional[str] = None
    failure_message: Optional[str] = None


class XboxBalanceSnapshotOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=_to_camel)

    id: int
    account_id: int
    currency: str
    balance: Decimal
    captured_at: str


def _serialize_sync_batch(b: XboxSyncBatch) -> XboxSyncBatchOut:
    return XboxSyncBatchOut(
        id=b.id,
        account_id=b.account_id,
        started_at=b.started_at.isoformat() if b.started_at else "",
        finished_at=b.finished_at.isoformat() if b.finished_at else None,
        requested_count=b.requested_count,
        fetched_count=b.fetched_count,
        success=b.success,
        failure_category=b.failure_category,
        failure_message=b.failure_message,
    )


def _serialize_balance_snapshot(s: XboxBalanceSnapshot) -> XboxBalanceSnapshotOut:
    return XboxBalanceSnapshotOut(
        id=s.id,
        account_id=s.account_id,
        currency=s.currency,
        balance=s.balance,
        captured_at=s.captured_at.isoformat() if s.captured_at else "",
    )


@router.post(
    "/sync/orders",
    response_model=dict,
    status_code=status.HTTP_200_OK,
)
def sync_orders_endpoint(
    request: XboxSyncRequest,
    db: Session = Depends(get_db),
) -> dict:
    """触发 Microsoft 订单同步（阶段 1: mock 数据）。

    返回 ``{batchId, success, ordersAdded, ordersSkipped, balance, failure}``。
    """
    account = get_account_or_404(db, request.account_id)
    try:
        result = trigger_sync(db, account, count=request.count)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    return result


# ---------------------------------------------------------------------------
# 刷新余额 (CEO 2026-05-12 Q2: 单账号 + 全部 — 用于判断出入库)
# ---------------------------------------------------------------------------


@router.post(
    "/accounts/{account_id}/refresh-balance",
    response_model=XboxAccountOut,
    response_model_by_alias=True,
)
def refresh_account_balance_endpoint(
    account_id: int,
    db: Session = Depends(get_db),
) -> XboxAccountOut:
    """刷新单个账号的微软余额(只拉余额,不拉订单)。

    成功时:
    - 更新 account.local_balance
    - 自动识别国家(USD→US, GBP→UK) → 更新 country/currency + country_identified=True
    - 写余额快照
    - 写审计日志

    失败时 (账号未设邮箱/密码 / 已停用) 返回 200 但 status_message 含原因,
    不抛 4xx — 因为这是"刷新"语义,失败的账号也要让 CEO 看到状态。
    """
    account = get_account_or_404(db, account_id)
    refresh_account_balance(db, account)
    db.commit()
    db.refresh(account)
    return serialize_account(account)


class XboxRefreshAllResult(BaseModel):
    """全部刷新结果摘要 — 一次性看到所有账号的余额变化。"""

    model_config = ConfigDict(populate_by_name=True, alias_generator=_to_camel)

    total: int
    succeeded: int
    failed: int
    accounts: list[XboxAccountOut]


@router.post(
    "/refresh-all-balances",
    response_model=XboxRefreshAllResult,
    response_model_by_alias=True,
)
def refresh_all_balances_endpoint(db: Session = Depends(get_db)) -> XboxRefreshAllResult:
    """[已废弃, 但保留向后兼容] 同步刷新所有账号余额, 全部跑完才返回。

    CEO 2026-05-17: 改用 POST /xbox/refresh-jobs 异步启动 + GET 轮询进度,
    7 个账号一起跑要 5-10 分钟, HTTP 长连接会超时, 同步版前端是看不到结果的。
    """
    accounts = service_list_accounts(db, status=XboxAccountStatus.ACTIVE.value)
    succeeded = 0
    failed = 0
    out_accounts: list[XboxAccountOut] = []
    for account in accounts:
        result = refresh_account_balance(db, account)
        if result["success"]:
            succeeded += 1
        else:
            failed += 1
    db.commit()
    # 重新加载所有账号
    accounts = service_list_accounts(db, status=XboxAccountStatus.ACTIVE.value)
    out_accounts = [serialize_account(a) for a in accounts]
    return XboxRefreshAllResult(
        total=len(accounts),
        succeeded=succeeded,
        failed=failed,
        accounts=out_accounts,
    )


# ---------------------------------------------------------------------------
# 异步批量刷新 (CEO 2026-05-17: 进度条 UI 用)
# ---------------------------------------------------------------------------


class XboxRefreshJobStart(BaseModel):
    """启动任务返回的 job_id。"""

    model_config = ConfigDict(populate_by_name=True, alias_generator=_to_camel)

    job_id: str
    total: int


class XboxAccountRefreshResult(BaseModel):
    """单个账号刷新结果(progress 展示用)。"""

    model_config = ConfigDict(populate_by_name=True, alias_generator=_to_camel)

    account_id: int
    account_name: str
    success: bool
    balance: Optional[str] = None
    currency: Optional[str] = None
    message: Optional[str] = None


class XboxRefreshJobStatus(BaseModel):
    """整批刷新当前进度。"""

    model_config = ConfigDict(populate_by_name=True, alias_generator=_to_camel)

    job_id: str
    total: int
    completed: int
    succeeded: int
    failed: int
    current_account_id: Optional[int] = None
    current_account_name: Optional[str] = None
    done: bool
    results: list[XboxAccountRefreshResult]


@router.post(
    "/refresh-jobs",
    response_model=XboxRefreshJobStart,
    response_model_by_alias=True,
)
def start_refresh_job(db: Session = Depends(get_db)) -> XboxRefreshJobStart:
    """启动异步批量刷新, 立即返回 job_id, 前端轮询 GET /xbox/refresh-jobs/{id}。

    内部开一个 daemon thread 串行跑每个账号, 每跑完一个把结果写进 job 状态。
    """
    import threading
    from src.database import SessionLocal
    from src.services.xbox_refresh_jobs import (
        AccountRefreshResult,
        append_result,
        create_job,
        finish_job,
        update_progress,
    )

    accounts = service_list_accounts(db, status=XboxAccountStatus.ACTIVE.value)
    account_ids = [a.id for a in accounts]
    account_names = {a.id: a.name for a in accounts}

    job = create_job(total=len(account_ids))

    def _runner(job_id: str, ids: list[int]) -> None:
        """在独立线程串行刷新每个账号. 每个账号用独立 DB session。"""
        for aid in ids:
            name = account_names.get(aid, f"#{aid}")
            update_progress(job_id, current_account_id=aid, current_account_name=name)
            session = SessionLocal()
            try:
                acc = session.get(XboxAccount, aid)
                if acc is None:
                    append_result(job_id, AccountRefreshResult(
                        account_id=aid, account_name=name, success=False,
                        message="账号不存在",
                    ))
                    continue
                result = refresh_account_balance(session, acc)
                session.commit()
                append_result(job_id, AccountRefreshResult(
                    account_id=aid,
                    account_name=name,
                    success=bool(result.get("success")),
                    balance=result.get("balance"),
                    currency=result.get("currency"),
                    message=result.get("message"),
                ))
            except Exception as exc:
                session.rollback()
                append_result(job_id, AccountRefreshResult(
                    account_id=aid, account_name=name, success=False,
                    message=f"系统异常: {type(exc).__name__}: {exc}",
                ))
            finally:
                session.close()
        finish_job(job_id)

    threading.Thread(
        target=_runner, args=(job.job_id, account_ids), daemon=True
    ).start()

    return XboxRefreshJobStart(job_id=job.job_id, total=job.total)


@router.get(
    "/refresh-jobs/{job_id}",
    response_model=XboxRefreshJobStatus,
    response_model_by_alias=True,
)
def get_refresh_job_status(job_id: str) -> XboxRefreshJobStatus:
    """查询批量刷新进度. 前端每 2 秒轮询一次。"""
    from src.services.xbox_refresh_jobs import get_job

    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在(可能已被清理或后端重启)")
    return XboxRefreshJobStatus(
        job_id=job.job_id,
        total=job.total,
        completed=job.completed,
        succeeded=job.succeeded,
        failed=job.failed,
        current_account_id=job.current_account_id,
        current_account_name=job.current_account_name,
        done=job.finished_at is not None,
        results=[
            XboxAccountRefreshResult(
                account_id=r.account_id,
                account_name=r.account_name,
                success=r.success,
                balance=r.balance,
                currency=r.currency,
                message=r.message,
            )
            for r in job.results
        ],
    )


@router.get(
    "/sync/batches",
    response_model=list[XboxSyncBatchOut],
    response_model_by_alias=True,
)
def list_sync_batches_endpoint(
    account_id: Optional[int] = Query(None, alias="accountId"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[XboxSyncBatchOut]:
    """查同步批次历史(最新在前)。"""
    batches = list_sync_batches(db, account_id=account_id, limit=limit)
    return [_serialize_sync_batch(b) for b in batches]


@router.get(
    "/accounts/{account_id}/balance-snapshots",
    response_model=list[XboxBalanceSnapshotOut],
    response_model_by_alias=True,
)
def list_balance_snapshots_endpoint(
    account_id: int,
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[XboxBalanceSnapshotOut]:
    """查账号余额快照(最新在前)。"""
    get_account_or_404(db, account_id)
    snapshots = list_balance_snapshots(db, account_id, limit=limit)
    return [_serialize_balance_snapshot(s) for s in snapshots]
