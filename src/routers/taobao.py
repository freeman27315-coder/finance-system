"""Taobao shop API routes."""
from __future__ import annotations

from decimal import Decimal
from io import BytesIO
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, case, func, select, text
from sqlalchemy.orm import Session

from src.database import get_db
from src.models.taobao import (
    TaobaoOrder,
    TaobaoOrderPaymentMethod,
    TaobaoOrderStatus,
    TaobaoShop,
)
from src.models.wallet import (
    Currency,
    Wallet,
    WalletTransaction,
    WalletType,
    credit,
    debit,
)
from src.services.taobao import list_taobao_shops
from src.services.taobao_import import (
    ImportReport,
    TaobaoImportError,
    import_qianniu_workbook,
)
from src.services.taobao_maturity import calculate_pending_maturity


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
    aggregator_matured_amount: Decimal
    aggregator_matured_count: int
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
    auto_released_amount: Decimal
    auto_released_count: int
    total_fee_amount: Decimal
    errors: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 金流端点请求 / 响应模型
# ---------------------------------------------------------------------------


class WithdrawRequest(BaseModel):
    amount: Decimal = Field(..., gt=0)
    remark: Optional[str] = Field(None, max_length=500)


class TransferToAssetRequest(BaseModel):
    target_wallet_id: Optional[int] = Field(None, description="可选目标钱包 id；不传则用 shop.store_alipay_wallet 作为默认目标")
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


class WalletDailySummaryOut(BaseModel):
    """钱包按日聚合：每天的入账总额、出账总额、净额、笔数。

    ``date`` 取 ``WalletTransaction.created_at`` 的日期（中国时区,
    系统时间已统一 UTC+8）。
    """

    model_config = ConfigDict(populate_by_name=True, alias_generator=_to_camel)

    date: str  # YYYY-MM-DD
    in_amount: Decimal
    out_amount: Decimal
    net_amount: Decimal
    count: int


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


def serialize_shop(shop: TaobaoShop, db: Session) -> TaobaoShopOut:
    matured_amount, matured_count = calculate_pending_maturity(
        db, shop.aggregator_frozen_wallet_id
    )
    return TaobaoShopOut(
        id=shop.id,
        name=shop.name,
        store_alipay_wallet=_serialize_wallet(shop.store_alipay_wallet),
        unconfirmed_alipay=_serialize_wallet(shop.unconfirmed_alipay_wallet),
        unconfirmed_wechat=_serialize_wallet(shop.unconfirmed_wechat_wallet),
        aggregator_frozen=_serialize_wallet(shop.aggregator_frozen_wallet),
        aggregator_available=_serialize_wallet(shop.aggregator_available_wallet),
        bank_card=_serialize_wallet(shop.bank_card_wallet),
        aggregator_matured_amount=matured_amount,
        aggregator_matured_count=matured_count,
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
        auto_released_amount=Decimal(report.auto_released_amount),
        auto_released_count=report.auto_released_count,
        total_fee_amount=Decimal(report.total_fee_amount),
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
    return [serialize_shop(shop, db) for shop in list_taobao_shops(db)]


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
    """银行卡 → 目标支付宝（实际金流：银行卡 ↔ 支付宝绑定，钱不经店铺支付宝中转）。

    body 行为：
    - target_wallet_id 不传 → 默认目标 = shop.store_alipay_wallet（向后兼容）
    - target_wallet_id 传 → 校验合法性后用指定目标

    校验：
    - shop / wallet 存在性
    - amount > 0；银行卡余额足；
    - 兔仔（store_alipay_wallet.type==TAOBAO）：传非自身 store_alipay_wallet 的 target → 400
    - 丙火/小小（store_alipay_wallet.type==ASSET_RMB）：target 必须是 type=ASSET_RMB+currency=CNY+父钱包 name="支付宝钱包" 子钱包
    - target 不存在 → 404；已软删 → 400；==银行卡本身 → 400；is_group → 400
    """
    shop = _get_shop_or_404(db, shop_id)

    bank_card = shop.bank_card_wallet
    store_alipay = shop.store_alipay_wallet

    # 1. 解析目标钱包：传了 → 校验后取，没传 → 用 shop.store_alipay_wallet
    if request.target_wallet_id is not None:
        target_wallet = db.get(Wallet, request.target_wallet_id)
        if target_wallet is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="目标钱包不存在",
            )
        if target_wallet.deleted_at is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="目标钱包已删除",
            )
        if target_wallet.id == bank_card.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="不能转给自己",
            )
        if target_wallet.is_group:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="分组钱包不可作为目标",
            )

        # 兔仔约束：store_alipay_wallet.type==TAOBAO 时只能转回自身 store_alipay_wallet
        store_type = (
            store_alipay.type.value
            if isinstance(store_alipay.type, WalletType)
            else store_alipay.type
        )
        if store_type == WalletType.TAOBAO.value:
            if target_wallet.id != store_alipay.id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="兔仔店铺只能转回自身店铺支付宝",
                )
        elif store_type == WalletType.ASSET_RMB.value:
            # 丙火/小小约束：target 必须是 type=ASSET_RMB+currency=CNY+父钱包 name="支付宝钱包"
            target_type = (
                target_wallet.type.value
                if isinstance(target_wallet.type, WalletType)
                else target_wallet.type
            )
            target_currency = (
                target_wallet.currency.value
                if isinstance(target_wallet.currency, Currency)
                else target_wallet.currency
            )
            parent_ok = False
            if target_wallet.parent_id is not None:
                parent = db.get(Wallet, target_wallet.parent_id)
                if parent is not None and parent.name == "支付宝钱包":
                    parent_ok = True
            if (
                target_type != WalletType.ASSET_RMB.value
                or target_currency != Currency.CNY.value
                or not parent_ok
            ):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="目标必须是资产支付宝下的子钱包",
                )
    else:
        target_wallet = store_alipay

    # 2. 金额
    if request.amount is not None:
        amount = Decimal(str(request.amount))
    else:
        amount = Decimal(bank_card.balance)

    if amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="可转金额必须大于 0",
        )

    # 3. 备注：默认带目标名以便审计；CEO 可覆盖
    remark = request.remark or f"提现 → {target_wallet.name}"

    try:
        debit(db, bank_card.id, amount, remark=remark)
        credit(db, target_wallet.id, amount, remark=remark)
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
    db.refresh(target_wallet)
    return FlowReportOut(
        amount=amount,
        from_wallet_id=bank_card.id,
        from_wallet_balance=Decimal(bank_card.balance),
        to_wallet_id=target_wallet.id,
        to_wallet_balance=Decimal(target_wallet.balance),
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


@router.get(
    "/shops/{shop_id}/wallets/{wallet_id}/daily-summary",
    response_model=list[WalletDailySummaryOut],
    response_model_by_alias=True,
)
def list_wallet_daily_summary_for_shop(
    shop_id: int,
    wallet_id: int,
    from_: Optional[str] = Query(None, alias="from", description="起始日期 YYYY-MM-DD,闭区间"),
    to: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD,闭区间"),
    db: Session = Depends(get_db),
) -> list[WalletDailySummaryOut]:
    """单钱包按日聚合：每天的入账/出账/净额/笔数,按业务日期降序。

    业务日期口径（CEO 2026-05-08 确认,见 .claude/skills/taobao-cashflow-rules）：
    - IN 流水有 order 关联 → 按 order 业务日期：
      - received       → ``order.confirmed_at``（"5/6 这天确认收货的钱进了店铺支付宝"）
      - shipped_unconfirmed → ``order.shipped_at``（"5/4 这天发货的钱进了在途"）
    - 其他流水（OUT、reconcile 撤旧、release、手动操作）→ ``tx.created_at``（操作日）

    LEFT JOIN 找 order：``TaobaoOrder.bookkeeping_tx_id = WalletTransaction.id``
    无关联或非 IN 流水落入 ELSE 分支。

    ``from``/``to`` 闭区间过滤的是 **业务日期**（CASE 后的结果）。
    所有时间已统一中国本地（PR #92）,DATE() 直接取 YYYY-MM-DD。
    """
    shop = _get_shop_or_404(db, shop_id)

    if wallet_id not in _shop_wallet_ids(shop):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="该钱包不属于本店铺",
        )

    # 业务日期 CASE 表达式（优先级从高到低）
    # 1. IN 流水 + business_date 不为空 → 用 business_date
    #    （聚合释放写入 available IN 时填 mature_at 那天）
    # 2. IN 流水 + order received → confirmed_at
    # 3. IN 流水 + order shipped_unconfirmed → shipped_at
    # 4. 其他（OUT、reconcile、手动操作、历史无 business_date 的 release）→ tx.created_at
    business_date = case(
        (
            and_(
                WalletTransaction.direction == "in",
                WalletTransaction.business_date.is_not(None),
            ),
            WalletTransaction.business_date,
        ),
        (
            and_(
                WalletTransaction.direction == "in",
                TaobaoOrder.status == TaobaoOrderStatus.RECEIVED.value,
                TaobaoOrder.confirmed_at.is_not(None),
            ),
            func.date(TaobaoOrder.confirmed_at),
        ),
        (
            and_(
                WalletTransaction.direction == "in",
                TaobaoOrder.status == TaobaoOrderStatus.SHIPPED_UNCONFIRMED.value,
                TaobaoOrder.shipped_at.is_not(None),
            ),
            func.date(TaobaoOrder.shipped_at),
        ),
        else_=func.date(WalletTransaction.created_at),
    )

    in_sum = func.sum(
        case(
            (WalletTransaction.direction == "in", WalletTransaction.amount),
            else_=0,
        )
    )
    out_sum = func.sum(
        case(
            (WalletTransaction.direction == "out", WalletTransaction.amount),
            else_=0,
        )
    )

    stmt = (
        select(
            business_date.label("d"),
            in_sum.label("in_amt"),
            out_sum.label("out_amt"),
            func.count(WalletTransaction.id).label("cnt"),
        )
        .select_from(WalletTransaction)
        .outerjoin(
            TaobaoOrder,
            TaobaoOrder.bookkeeping_tx_id == WalletTransaction.id,
        )
        .where(WalletTransaction.wallet_id == wallet_id)
    )
    if from_:
        stmt = stmt.where(business_date >= from_)
    if to:
        stmt = stmt.where(business_date <= to)
    stmt = stmt.group_by(business_date).order_by(text("d DESC"))

    rows = db.execute(stmt).all()

    out: list[WalletDailySummaryOut] = []
    for row in rows:
        in_amount = Decimal(row.in_amt or 0)
        out_amount = Decimal(row.out_amt or 0)
        out.append(
            WalletDailySummaryOut(
                date=str(row.d),
                in_amount=in_amount,
                out_amount=out_amount,
                net_amount=in_amount - out_amount,
                count=int(row.cnt),
            )
        )
    return out
