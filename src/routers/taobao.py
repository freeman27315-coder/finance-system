"""Taobao shop API routes."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from io import BytesIO
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.database import get_db
from src.models.taobao import (
    TaobaoOrder,
    TaobaoOrderPaymentMethod,
    TaobaoOrderStatus,
    TaobaoShop,
)
from src.models.wallet import (
    TransactionDirection,
    Wallet,
    WalletTransaction,
    credit,
    debit,
)
from src.services.taobao import list_taobao_shops
from src.services.taobao_import import (
    ImportReport,
    TaobaoImportError,
    import_qianniu_workbook,
)


router = APIRouter(prefix="/taobao", tags=["taobao"])


def _to_camel(snake: str) -> str:
    head, *tail = snake.split("_")
    return head + "".join(part.title() for part in tail)


class TaobaoShopWalletOut(BaseModel):
    id: int
    name: str
    balance: Decimal
    type: str


class TaobaoShopOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=_to_camel)

    id: int
    name: str
    store_alipay_wallet: TaobaoShopWalletOut
    unconfirmed_alipay: TaobaoShopWalletOut
    unconfirmed_wechat: TaobaoShopWalletOut
    aggregator_frozen: TaobaoShopWalletOut
    aggregator_available: TaobaoShopWalletOut
    bank_card: TaobaoShopWalletOut
    remark: Optional[str] = None
    created_at: str


class TaobaoImportReportOut(BaseModel):
    """ImportReport 的 camelCase 输出。"""

    model_config = ConfigDict(populate_by_name=True, alias_generator=_to_camel)

    shop_name: str
    total_rows_parsed: int
    created_orders: int
    status_changed_orders: int
    closed_reverted: int
    skipped_no_change: int
    skipped_unpaid_or_unshipped: int
    skipped_unknown_payment: int
    errors: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 金流端点请求 / 响应模型
# ---------------------------------------------------------------------------


class ReleaseReportOut(BaseModel):
    """聚合冻结一键解冻响应。"""

    model_config = ConfigDict(populate_by_name=True, alias_generator=_to_camel)

    matured_count: int
    matured_amount: Decimal
    frozen_balance_after: Decimal
    available_balance_after: Decimal


class WithdrawRequest(BaseModel):
    amount: Decimal = Field(..., gt=0)
    remark: Optional[str] = Field(None, max_length=500)


class TransferToAssetRequest(BaseModel):
    amount: Optional[Decimal] = Field(None, gt=0)
    remark: Optional[str] = Field(None, max_length=500)


class FlowReportOut(BaseModel):
    """提现 / 转资产 通用响应（金额 + 双钱包余额）。"""

    model_config = ConfigDict(populate_by_name=True, alias_generator=_to_camel)

    amount: Decimal
    from_wallet_id: int
    from_wallet_balance: Decimal
    to_wallet_id: int
    to_wallet_balance: Decimal
    remark: str


class TaobaoOrderOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=_to_camel)

    id: int
    order_number: str
    payment_method: str
    amount: Decimal
    status: str
    bookkeeping_wallet_id: Optional[int] = None
    bookkeeping_tx_id: Optional[int] = None
    shipped_at: Optional[str] = None
    received_at: Optional[str] = None
    last_synced_at: str
    recorded_at: str


class WalletTransactionOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=_to_camel)

    id: int
    wallet_id: int
    amount: Decimal
    direction: str
    remark: Optional[str] = None
    created_at: str
    mature_at: Optional[str] = None


# ---------------------------------------------------------------------------
# 序列化 helper
# ---------------------------------------------------------------------------


def _serialize_wallet(wallet: Wallet) -> TaobaoShopWalletOut:
    wallet_type = wallet.type.value if hasattr(wallet.type, "value") else str(wallet.type)
    return TaobaoShopWalletOut(
        id=wallet.id,
        name=wallet.name,
        balance=wallet.balance,
        type=wallet_type,
    )


def serialize_shop(shop: TaobaoShop) -> TaobaoShopOut:
    return TaobaoShopOut(
        id=shop.id,
        name=shop.name,
        store_alipay_wallet=_serialize_wallet(shop.store_alipay_wallet),
        unconfirmed_alipay=_serialize_wallet(shop.unconfirmed_alipay_wallet),
        unconfirmed_wechat=_serialize_wallet(shop.unconfirmed_wechat_wallet),
        aggregator_frozen=_serialize_wallet(shop.aggregator_frozen_wallet),
        aggregator_available=_serialize_wallet(shop.aggregator_available_wallet),
        bank_card=_serialize_wallet(shop.bank_card_wallet),
        remark=shop.remark,
        created_at=shop.created_at.isoformat() if shop.created_at else "",
    )


def _serialize_report(report: ImportReport) -> TaobaoImportReportOut:
    return TaobaoImportReportOut(
        shop_name=report.shop_name,
        total_rows_parsed=report.total_rows_parsed,
        created_orders=report.created_orders,
        status_changed_orders=report.status_changed_orders,
        closed_reverted=report.closed_reverted,
        skipped_no_change=report.skipped_no_change,
        skipped_unpaid_or_unshipped=report.skipped_unpaid_or_unshipped,
        skipped_unknown_payment=report.skipped_unknown_payment,
        errors=list(report.errors),
    )


def _enum_value(value) -> str:
    if hasattr(value, "value"):
        return value.value
    return str(value)


def _serialize_order(order: TaobaoOrder) -> TaobaoOrderOut:
    return TaobaoOrderOut(
        id=order.id,
        order_number=order.order_number,
        payment_method=_enum_value(order.payment_method),
        amount=Decimal(order.amount),
        status=_enum_value(order.status),
        bookkeeping_wallet_id=order.bookkeeping_wallet_id,
        bookkeeping_tx_id=order.bookkeeping_tx_id,
        shipped_at=order.shipped_at.isoformat() if order.shipped_at else None,
        received_at=order.received_at.isoformat() if order.received_at else None,
        last_synced_at=order.last_synced_at.isoformat() if order.last_synced_at else "",
        recorded_at=order.recorded_at.isoformat() if order.recorded_at else "",
    )


def _serialize_transaction(tx: WalletTransaction) -> WalletTransactionOut:
    return WalletTransactionOut(
        id=tx.id,
        wallet_id=tx.wallet_id,
        amount=Decimal(tx.amount),
        direction=_enum_value(tx.direction),
        remark=tx.remark,
        created_at=tx.created_at.isoformat() if tx.created_at else "",
        mature_at=tx.mature_at.isoformat() if tx.mature_at else None,
    )


# ---------------------------------------------------------------------------
# 通用 helper
# ---------------------------------------------------------------------------


def _get_shop_or_404(db: Session, shop_id: int) -> TaobaoShop:
    shop = db.get(TaobaoShop, shop_id)
    if shop is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="店铺不存在")
    return shop


def _shop_wallet_ids(shop: TaobaoShop) -> set[int]:
    """该 shop 关联的所有钱包 id（5 内部 + store_alipay_wallet,共 6 个）。"""
    return {
        shop.unconfirmed_alipay_wallet_id,
        shop.unconfirmed_wechat_wallet_id,
        shop.aggregator_frozen_wallet_id,
        shop.aggregator_available_wallet_id,
        shop.bank_card_wallet_id,
        shop.store_alipay_wallet_id,
    }


# ---------------------------------------------------------------------------
# 端点
# ---------------------------------------------------------------------------


@router.get("/shops", response_model=list[TaobaoShopOut], response_model_by_alias=True)
def get_shops(db: Session = Depends(get_db)) -> list[TaobaoShopOut]:
    return [serialize_shop(shop) for shop in list_taobao_shops(db)]


@router.post(
    "/shops/{shop_id}/import",
    response_model=TaobaoImportReportOut,
    response_model_by_alias=True,
    status_code=status.HTTP_200_OK,
)
def import_qianniu_excel(
    shop_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> TaobaoImportReportOut:
    """上传千牛后台导出的 .xlsx，按规则入账每条订单并对老订单做 reconcile。

    - 404：店铺不存在
    - 400：文件不是 .xlsx 或表头/列结构不符
    - 整个导入是单一事务：任何一行抛异常都 rollback，不会半成功
    """
    # 1. 店铺存在性校验
    shop = _get_shop_or_404(db, shop_id)

    # 2. 文件类型校验（按后缀；content-type 在不同客户端表现不一）
    filename = (file.filename or "").lower()
    if not filename.endswith(".xlsx"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="仅支持 .xlsx 文件",
        )

    # 3. 读取 + 解析 + 入账（原子事务）
    raw_bytes = file.file.read()
    if not raw_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="文件为空",
        )

    try:
        report = import_qianniu_workbook(db, shop, BytesIO(raw_bytes))
        db.commit()
    except TaobaoImportError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise

    return _serialize_report(report)


@router.post(
    "/shops/{shop_id}/aggregator/release",
    response_model=ReleaseReportOut,
    response_model_by_alias=True,
)
def release_matured_aggregator(
    shop_id: int,
    db: Session = Depends(get_db),
) -> ReleaseReportOut:
    """一键解冻所有到期聚合冻结流水。

    - 查询 ``aggregator_frozen_wallet`` 上 ``mature_at <= now()`` 的所有 in 流水
    - 仅解冻"仍有效"的流水（其 id 仍是某 TaobaoOrder 的 bookkeeping_tx_id）
      —— 防御性，避免把已被 reconcile 撤销的旧流水重复解冻
    - 把累计金额从 frozen debit、credit 到 available
    - 单一事务；无到期流水返回 200 + matured_count=0
    """
    shop = _get_shop_or_404(db, shop_id)
    now = datetime.now(timezone.utc)

    matured_txs = list(
        db.scalars(
            select(WalletTransaction)
            .where(
                WalletTransaction.wallet_id == shop.aggregator_frozen_wallet_id,
                WalletTransaction.direction == TransactionDirection.IN.value,
                WalletTransaction.mature_at.is_not(None),
                WalletTransaction.mature_at <= now,
            )
            .order_by(WalletTransaction.id)
        )
    )

    # 防御：只解冻仍被某 order.bookkeeping_tx_id 引用的（说明状态未变化、未被撤）
    if matured_txs:
        tx_ids = [tx.id for tx in matured_txs]
        active_tx_ids = set(
            db.scalars(
                select(TaobaoOrder.bookkeeping_tx_id)
                .where(TaobaoOrder.bookkeeping_tx_id.in_(tx_ids))
            )
        )
        matured_txs = [tx for tx in matured_txs if tx.id in active_tx_ids]

    matured_count = len(matured_txs)
    matured_amount = sum((Decimal(tx.amount) for tx in matured_txs), Decimal("0"))

    if matured_count > 0:
        try:
            remark = f"解冻 {matured_count} 笔到期"
            debit(db, shop.aggregator_frozen_wallet_id, matured_amount, remark=remark)
            credit(db, shop.aggregator_available_wallet_id, matured_amount, remark=remark)
            db.commit()
        except ValueError as exc:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc
        except Exception:
            db.rollback()
            raise

    db.refresh(shop.aggregator_frozen_wallet)
    db.refresh(shop.aggregator_available_wallet)
    return ReleaseReportOut(
        matured_count=matured_count,
        matured_amount=matured_amount,
        frozen_balance_after=Decimal(shop.aggregator_frozen_wallet.balance),
        available_balance_after=Decimal(shop.aggregator_available_wallet.balance),
    )


@router.post(
    "/shops/{shop_id}/withdraw",
    response_model=FlowReportOut,
    response_model_by_alias=True,
)
def withdraw_to_bank_card(
    shop_id: int,
    request: WithdrawRequest,
    db: Session = Depends(get_db),
) -> FlowReportOut:
    """可提现 → 银行卡（CEO 输金额）。"""
    shop = _get_shop_or_404(db, shop_id)
    amount = Decimal(str(request.amount))
    remark = request.remark or "提现到银行卡"

    available = shop.aggregator_available_wallet
    bank_card = shop.bank_card_wallet

    try:
        debit(db, available.id, amount, remark=remark)
        credit(db, bank_card.id, amount, remark=remark)
        db.commit()
    except ValueError as exc:
        db.rollback()
        message = str(exc)
        if "insufficient" in message:
            message = "可提现余额不足"
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message) from exc
    except Exception:
        db.rollback()
        raise

    db.refresh(available)
    db.refresh(bank_card)
    return FlowReportOut(
        amount=amount,
        from_wallet_id=available.id,
        from_wallet_balance=Decimal(available.balance),
        to_wallet_id=bank_card.id,
        to_wallet_balance=Decimal(bank_card.balance),
        remark=remark,
    )


@router.post(
    "/shops/{shop_id}/transfer-to-store-alipay",
    response_model=FlowReportOut,
    response_model_by_alias=True,
)
def transfer_bank_card_to_store_alipay(
    shop_id: int,
    request: TransferToAssetRequest,
    db: Session = Depends(get_db),
) -> FlowReportOut:
    """银行卡 → 店铺支付宝（A/B 类店铺均可调）。

    - 丙火/小小：bank_card debit + 资产支付宝子钱包 credit（实际金流）
    - 兔仔：bank_card debit + 兔仔电玩支付宝（type=TAOBAO）credit（账面记账）
    - amount 不传时默认 = 银行卡当前余额
    - 银行卡余额不足或为 0 → 400
    """
    shop = _get_shop_or_404(db, shop_id)

    bank_card = shop.bank_card_wallet
    store_alipay = shop.store_alipay_wallet

    if request.amount is not None:
        amount = Decimal(str(request.amount))
    else:
        amount = Decimal(bank_card.balance)

    if amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="可转金额必须大于 0",
        )

    remark = request.remark or "提现"

    try:
        debit(db, bank_card.id, amount, remark=remark)
        credit(db, store_alipay.id, amount, remark=remark)
        db.commit()
    except ValueError as exc:
        db.rollback()
        message = str(exc)
        if "insufficient" in message:
            message = "银行卡余额不足"
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message) from exc
    except Exception:
        db.rollback()
        raise

    db.refresh(bank_card)
    db.refresh(store_alipay)
    return FlowReportOut(
        amount=amount,
        from_wallet_id=bank_card.id,
        from_wallet_balance=Decimal(bank_card.balance),
        to_wallet_id=store_alipay.id,
        to_wallet_balance=Decimal(store_alipay.balance),
        remark=remark,
    )


@router.get(
    "/shops/{shop_id}/orders",
    response_model=list[TaobaoOrderOut],
    response_model_by_alias=True,
)
def list_shop_orders(
    shop_id: int,
    status_filter: Optional[str] = Query(None, alias="status"),
    payment_method: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[TaobaoOrderOut]:
    """订单列表 + 状态过滤 + 分页（按 last_synced_at desc）。"""
    _get_shop_or_404(db, shop_id)

    stmt = select(TaobaoOrder).where(TaobaoOrder.shop_id == shop_id)

    if status_filter is not None:
        # 校验枚举值；非法值返回 400
        try:
            status_enum = TaobaoOrderStatus(status_filter)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"非法 status: {status_filter}",
            ) from exc
        stmt = stmt.where(TaobaoOrder.status == status_enum.value)

    if payment_method is not None:
        try:
            method_enum = TaobaoOrderPaymentMethod(payment_method)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"非法 payment_method: {payment_method}",
            ) from exc
        stmt = stmt.where(TaobaoOrder.payment_method == method_enum.value)

    stmt = stmt.order_by(TaobaoOrder.last_synced_at.desc(), TaobaoOrder.id.desc()).limit(limit).offset(offset)

    orders = list(db.scalars(stmt))
    return [_serialize_order(order) for order in orders]


@router.get(
    "/shops/{shop_id}/wallets/{wallet_id}/transactions",
    response_model=list[WalletTransactionOut],
    response_model_by_alias=True,
)
def list_wallet_transactions_for_shop(
    shop_id: int,
    wallet_id: int,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[WalletTransactionOut]:
    """单钱包流水（含 mature_at），仅允许查询该店铺关联的钱包。"""
    shop = _get_shop_or_404(db, shop_id)

    if wallet_id not in _shop_wallet_ids(shop):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="该钱包不属于本店铺",
        )

    txs = list(
        db.scalars(
            select(WalletTransaction)
            .where(WalletTransaction.wallet_id == wallet_id)
            .order_by(WalletTransaction.id.desc())
            .limit(limit)
            .offset(offset)
        )
    )
    return [_serialize_transaction(tx) for tx in txs]
