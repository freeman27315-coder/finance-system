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

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.xbox import (
    XboxAccount,
    XboxOrder,
    XboxOrderStatus,
    XboxWalletItem,
    XboxWalletMethod,
)
from src.services.xbox_sale import create_or_merge_sale_record
from src.utils.time import china_now


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
        raw_data=raw_data,
        status=XboxOrderStatus.PENDING_COMPLETE.value,
    )
    session.add(order)
    session.flush()
    return order


def update_order_completion(
    session: Session,
    order: XboxOrder,
    *,
    sale_date: Optional[date] = None,
    product_name: Optional[str] = None,
    operator_name: Optional[str] = None,
    sale_price: Optional[Decimal] = None,
    sale_currency: Optional[str] = None,
    wallet_method_id: Optional[int] = None,
    wallet_item_id: Optional[int] = None,
    auto_convert: bool = True,
) -> tuple[XboxOrder, Optional[int]]:
    """更新订单的补齐字段。所有必填都到位时自动转销售记录。

    返回 ``(order, sale_record_id_or_None)``。
    """
    if sale_date is not None:
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
    order.last_updated_at = china_now()
    session.flush()

    sale_record_id: Optional[int] = None

    # 检查是否所有补齐字段都到位 → 自动转销售
    if auto_convert and _all_completion_fields_set(order):
        item = session.get(XboxWalletItem, order.wallet_item_id)
        if item is None:
            raise ValueError(f"备注模板 {order.wallet_item_id} 不存在")
        if not item.is_active:
            raise ValueError(f"备注模板 {item.label} 已停用")
        method = session.get(XboxWalletMethod, order.wallet_method_id)
        if method is None:
            raise ValueError(f"收款方式 {order.wallet_method_id} 不存在")

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

    return order, sale_record_id


def _all_completion_fields_set(order: XboxOrder) -> bool:
    return (
        order.sale_date is not None
        and bool(order.product_name)
        and bool(order.operator_name)
        and order.sale_price is not None
        and bool(order.sale_currency)
        and order.wallet_method_id is not None
        and order.wallet_item_id is not None
    )


def list_orders(
    session: Session,
    *,
    account_id: Optional[int] = None,
    status: Optional[str] = None,
) -> list[XboxOrder]:
    stmt = select(XboxOrder).order_by(XboxOrder.id.desc())
    if account_id is not None:
        stmt = stmt.where(XboxOrder.account_id == account_id)
    if status is not None:
        stmt = stmt.where(XboxOrder.status == status)
    return list(session.scalars(stmt))


def get_order_or_404(session: Session, order_id: int) -> Optional[XboxOrder]:
    return session.get(XboxOrder, order_id)
