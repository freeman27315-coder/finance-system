"""XBOX 订单服务（FR-04 同步 + FR-05 补齐）。

P0.2 阶段：
- 支持手动建订单（CEO Q3A：让 CEO 立刻能试用整套流程）
- 自动同步在 P2（FR-04 / IF-03）实现

补齐流程：
- 订单原始字段：order_no, amount_local, currency_local, exchange_rate, order_at
- 待补齐：sale_date, product_name, operator_name, sale_price, sale_currency,
         wallet_method_id, wallet_item_id
- 全部补齐 → 调 xbox_sale.create_or_merge_sale_record 转销售记录
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional, Union

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.xbox import (
    XboxAccount,
    XboxChangeLog,
    XboxOrder,
    XboxOrderStatus,
    XboxWalletItem,
    XboxWalletMethod,
)
from src.services.xbox_sale import create_or_merge_sale_record
from src.utils.time import china_now


def _log_order_change(
    session: Session,
    order_id: int,
    action: str,
    detail: str,
    operator: str = "manual",
) -> None:
    log = XboxChangeLog(
        entity_type="order",
        entity_id=order_id,
        action=action,
        detail=detail,
        operator=operator,
    )
    session.add(log)
    session.flush()


def create_order(
    session: Session,
    *,
    account: XboxAccount,
    order_no: str,
    amount_local: Decimal,
    currency_local: str,
    order_at: datetime,
    exchange_rate: Optional[Decimal] = None,
    raw_data: Optional[dict] = None,
) -> XboxOrder:
    """新建一条同步订单（手动或来自 Microsoft 抓取）。

    rmb_cost = amount_local × exchange_rate（exchange_rate 为空时取账号汇率）
    """
    if not order_no.strip():
        raise ValueError("订单号不能为空")
    existing = session.scalar(select(XboxOrder).where(XboxOrder.order_no == order_no))
    if existing is not None:
        raise ValueError(f"订单号 {order_no} 已存在")

    used_rate = exchange_rate if exchange_rate is not None else account.exchange_rate
    if used_rate is None:
        # 没汇率就 0 成本（CEO 后续可补)
        rmb_cost = Decimal("0")
        used_rate_value = None
    else:
        rmb_cost = (Decimal(amount_local) * Decimal(used_rate)).quantize(Decimal("0.000001"))
        used_rate_value = Decimal(used_rate)

    order = XboxOrder(
        account_id=account.id,
        order_no=order_no.strip(),
        amount_local=Decimal(amount_local),
        currency_local=currency_local,
        exchange_rate=used_rate_value,
        rmb_cost=rmb_cost,
        order_at=order_at,
        # CEO 2026-05-12: 销售日期 = 微软订单时间(中国时区精确到秒),系统自动填
        sale_date=order_at,
        raw_data=raw_data,
        status=XboxOrderStatus.PENDING_COMPLETE.value,
    )
    session.add(order)
    session.flush()
    _log_order_change(
        session,
        order.id,
        "created",
        f"订单号 {order_no.strip()},{amount_local} {currency_local},RMB 成本 {rmb_cost}",
    )
    return order


def update_order_completion(
    session: Session,
    order: XboxOrder,
    *,
    sale_date: Union[date, datetime, None] = None,
    product_name: Optional[str] = None,
    operator_name: Optional[str] = None,
    sale_price: Optional[Decimal] = None,
    sale_currency: Optional[str] = None,
    wallet_method_id: Optional[int] = None,
    wallet_item_id: Optional[int] = None,
    wallet_pool_id: Optional[int] = None,
    wallet_item_label: Optional[str] = None,
    auto_convert: bool = True,
) -> tuple[XboxOrder, Optional[int]]:
    """更新订单的补齐字段。所有必填都到位时自动转销售记录。

    返回 ``(order, sale_record_id_or_None)``。

    CEO 2026-05-20 #134: 新订单只用 wallet_pool_id 直接挂真实钱包,
    不再走 wallet_method_id + wallet_item_id 中间层。
    老订单字段保留(可空)。
    """
    from src.models.wallet import Wallet  # 局部 import

    if sale_date is not None:
        if isinstance(sale_date, date) and not isinstance(sale_date, datetime):
            order.sale_date = datetime.combine(sale_date, datetime.min.time())
        else:
            order.sale_date = sale_date
    if product_name is not None:
        order.product_name = product_name
    if operator_name is not None:
        order.operator_name = operator_name
    if sale_price is not None:
        order.sale_price = Decimal(sale_price)
    if sale_currency is not None:
        order.sale_currency = sale_currency
    if wallet_method_id is not None:
        order.wallet_method_id = wallet_method_id
    if wallet_item_id is not None:
        order.wallet_item_id = wallet_item_id
    # CEO 2026-05-20 #134: 新订单字段 — 持久化到 xbox_orders.wallet_pool_id
    if wallet_pool_id is not None:
        order.wallet_pool_id = wallet_pool_id

    order.last_updated_at = china_now()
    session.flush()

    sale_record_id: Optional[int] = None

    # 检查是否所有补齐字段都到位 → 自动转销售
    if auto_convert and _all_completion_fields_set(order):
        # CEO 2026-05-20 #134: 新订单走 wallet_pool_id 直挂真实钱包流程
        if order.wallet_pool_id is not None:
            wallet = session.get(Wallet, order.wallet_pool_id)
            if wallet is None or wallet.deleted_at is not None:
                raise ValueError(f"钱包 {order.wallet_pool_id} 不存在或已废弃")
            account = session.get(XboxAccount, order.account_id)
            record = create_or_merge_sale_record(
                session,
                account=account,
                sale_date=order.sale_date,
                product_name=order.product_name,
                operator_name=order.operator_name,
                sale_price=order.sale_price,
                sale_currency=order.sale_currency,
                wallet_method_id=None,
                wallet_item_id=None,
                wallet_item_label=wallet_item_label or wallet.name,
                wallet_pool_id=order.wallet_pool_id,
                order=order,
            )
            sale_record_id = record.id
            _log_order_change(
                session,
                order.id,
                "completed",
                f"补齐转销售 #{record.id} ({wallet.name},{order.sale_price} {order.sale_currency})",
            )
        else:
            # 老流程兼容: 用 method+item 路径(老订单可能走这里)
            item = session.get(XboxWalletItem, order.wallet_item_id) if order.wallet_item_id else None
            if item is None:
                raise ValueError("钱包未选(请填 walletPoolId 或老的 method/item)")
            account = session.get(XboxAccount, order.account_id)
            record = create_or_merge_sale_record(
                session,
                account=account,
                sale_date=order.sale_date,
                product_name=order.product_name,
                operator_name=order.operator_name,
                sale_price=order.sale_price,
                sale_currency=order.sale_currency,
                wallet_method_id=order.wallet_method_id,
                wallet_item_id=order.wallet_item_id,
                wallet_item_label=item.label,
                wallet_pool_id=item.wallet_pool_id,
                order=order,
            )
            sale_record_id = record.id
            _log_order_change(
                session,
                order.id,
                "completed",
                f"补齐转销售 #{record.id} ({item.label},{order.sale_price} {order.sale_currency})",
            )

    return order, sale_record_id


def _all_completion_fields_set(order: XboxOrder) -> bool:
    has_wallet = (
        order.wallet_pool_id is not None
        or (order.wallet_method_id is not None and order.wallet_item_id is not None)
    )
    return (
        order.sale_date is not None
        and bool(order.product_name)
        and bool(order.operator_name)
        and order.sale_price is not None
        and bool(order.sale_currency)
        and has_wallet
    )


def move_order_to_different_sale_record(
    session: Session,
    order: XboxOrder,
    new_wallet_method_id: int,
    new_wallet_item_id: int,
) -> tuple[Optional[int], int]:
    """拆单：把已转销售的订单从老销售记录移到新（按新 wallet_item_id）。

    返回 ``(老销售记录 id 或 None, 新销售记录 id)``。

    业务规则（CEO 2026-05-08 Q5:A 老销售记录变 0 时保留）：
    1. 老销售记录 sale_price -= 本订单 sale_price + 旧池子 debit
    2. 找到/新建新销售记录（同账号 + 新 wallet_item_id）
       - 如果已存在 → 合并(累加 sale_price + 新池 credit)
       - 不存在 → 新建 + 新池 credit
    3. 更新订单的 sale_record_id / wallet_method_id / wallet_item_id
    4. 旧记录变 0 时保留(状态变化不删)
    5. 写审计日志
    """
    from src.models.xbox import XboxSaleRecord, XboxWalletItem
    from src.models.wallet import credit, debit
    from src.services.xbox_sale import (
        _find_existing_sale_record,
        _validate_pool_currency,
        create_or_merge_sale_record,
    )

    if order.sale_record_id is None or order.status != XboxOrderStatus.CONVERTED.value:
        raise ValueError("订单未转销售,不能执行拆单逻辑")

    if order.sale_price is None or order.sale_price <= 0:
        raise ValueError("订单售价为空或 0,无法拆单")

    if order.wallet_item_id == new_wallet_item_id:
        return order.sale_record_id, order.sale_record_id  # 没变,no-op

    # 校验新 method/item 存在
    new_item = session.get(XboxWalletItem, new_wallet_item_id)
    if new_item is None:
        raise ValueError(f"新备注模板 {new_wallet_item_id} 不存在")
    new_method = session.get(XboxWalletMethod, new_wallet_method_id)
    if new_method is None:
        raise ValueError(f"新收款方式 {new_wallet_method_id} 不存在")

    # 获取老销售记录
    old_record = session.get(XboxSaleRecord, order.sale_record_id)
    if old_record is None:
        raise ValueError(f"老销售记录 {order.sale_record_id} 不存在")

    # 校验新池币种
    _validate_pool_currency(session, new_item.wallet_pool_id, order.sale_currency or old_record.sale_currency)

    order_sale_price = Decimal(order.sale_price)

    # 1) 老记录扣减 + 旧池 debit
    old_record_id = old_record.id
    new_total = Decimal(old_record.sale_price) - order_sale_price
    if new_total < 0:
        raise ValueError(f"老销售记录金额会变负({new_total}),数据可能已损坏")
    old_record.sale_price = new_total
    if order_sale_price > 0:
        debit(
            session,
            old_record.wallet_pool_id,
            order_sale_price,
            remark=f"XBOX 拆单 订单#{order.id} 从销售#{old_record.id} 移出",
        )

    from src.services.xbox_sale import _log_change as log_change

    log_change(
        session,
        "sale_record",
        old_record.id,
        "updated",
        f"拆单: 订单 #{order.id} 移出, -{order_sale_price} {old_record.sale_currency}, 余额 {new_total}",
    )

    # 2) 找/建新销售记录
    account = session.get(XboxAccount, order.account_id)
    new_record = _find_existing_sale_record(session, account.id, new_wallet_item_id)
    if new_record is not None:
        # 合到现有
        new_total_price = Decimal(new_record.sale_price) + order_sale_price
        new_record.sale_price = new_total_price
        new_record.last_updated_at = china_now()
        if order_sale_price > 0:
            tx = credit(
                session,
                new_record.wallet_pool_id,
                order_sale_price,
                remark=f"XBOX 拆单 订单#{order.id} 合入销售#{new_record.id}",
            )
            new_record.bookkeeping_tx_id = tx.id
        log_change(
            session,
            "sale_record",
            new_record.id,
            "merged",
            f"拆单接收: 订单 #{order.id}, +{order_sale_price} {order.sale_currency}, 总额 {new_total_price}",
        )
    else:
        new_record = create_or_merge_sale_record(
            session,
            account=account,
            sale_date=old_record.sale_date,
            product_name=order.product_name or "(拆单)",
            operator_name=order.operator_name or old_record.operator_name,
            sale_price=order_sale_price,
            sale_currency=order.sale_currency or old_record.sale_currency,
            wallet_method_id=new_wallet_method_id,
            wallet_item_id=new_wallet_item_id,
            wallet_item_label=new_item.label,
            wallet_pool_id=new_item.wallet_pool_id,
            order=None,  # 不通过 order 参数（避免 status 重置）
        )

    # 3) 更新订单关联
    order.sale_record_id = new_record.id
    order.wallet_method_id = new_wallet_method_id
    order.wallet_item_id = new_wallet_item_id
    order.last_updated_at = china_now()

    _log_order_change(
        session,
        order.id,
        "wallet_pool_changed",
        f"拆单: 销售#{old_record_id} → 销售#{new_record.id} (备注模板 → {new_item.label})",
    )

    session.flush()
    return old_record_id, new_record.id


def list_orders(
    session: Session,
    *,
    account_id: Optional[int] = None,
    status: Optional[str] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
) -> list[XboxOrder]:
    """列出订单。可按账号/状态过滤。``from_date``/``to_date`` 按订单时间(order_at)闭区间过滤。"""
    stmt = select(XboxOrder).order_by(XboxOrder.id.desc())
    if account_id is not None:
        stmt = stmt.where(XboxOrder.account_id == account_id)
    if status is not None:
        stmt = stmt.where(XboxOrder.status == status)
    if from_date is not None:
        stmt = stmt.where(XboxOrder.order_at >= datetime.combine(from_date, datetime.min.time()))
    if to_date is not None:
        # 闭区间: 加一天再 <  → 等同 <= 当天 23:59:59
        stmt = stmt.where(
            XboxOrder.order_at < datetime.combine(to_date, datetime.min.time()) + timedelta(days=1)
        )
    return list(session.scalars(stmt))


def get_order_or_404(session: Session, order_id: int) -> Optional[XboxOrder]:
    return session.get(XboxOrder, order_id)
