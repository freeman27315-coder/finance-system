"""XBOX 销售记录服务（FR-06 合单 + FR-07 资金池流入）。

业务规则（CEO 2026-05-08 确认）：
- 合单：同账号 + 同 wallet_item_id → 视为同一销售记录,售价相加
- 销售记录创建即 credit ``sale_price`` 到 ``wallet_pool_id``（Q2A）
- 改 sale_price → 资金池 diff 调整(Q2A)
- 改 wallet_pool_id → 旧池 debit + 新池 credit(Q3A)
- 不能撤销但可改字段（CEO 4B）
- sale_currency 必须和 wallet_pool 钱包 currency 一致

所有变更都通过 ``Wallet.balance`` 加减 + 写 ``WalletTransaction`` 流水。
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.wallet import (
    TransactionDirection,
    Wallet,
    WalletTransaction,
    credit,
    debit,
)
from src.models.xbox import (
    XboxAccount,
    XboxOrder,
    XboxOrderStatus,
    XboxSaleRecord,
    XboxWalletItem,
)
from src.utils.time import china_now


# 币种 → 钱包应该的 currency
CURRENCY_TO_WALLET_CURRENCY = {
    "CNY": "CNY",
    "USD": "USD",
    "USDT": "USDT",
    "TWD": "TWD",
}


def _validate_pool_currency(session: Session, wallet_pool_id: int, sale_currency: str) -> Wallet:
    """校验资金池钱包存在且币种与 sale_currency 一致。返回钱包对象。"""
    wallet = session.get(Wallet, wallet_pool_id)
    if wallet is None:
        raise ValueError(f"资金池钱包 {wallet_pool_id} 不存在")
    expected = CURRENCY_TO_WALLET_CURRENCY.get(sale_currency)
    if expected is None:
        raise ValueError(f"不支持的销售币种: {sale_currency}")
    actual = wallet.currency.value if hasattr(wallet.currency, "value") else wallet.currency
    if actual != expected:
        raise ValueError(
            f"资金池钱包币种 {actual} 与销售币种 {sale_currency} 不一致"
        )
    return wallet


def _find_existing_sale_record(
    session: Session,
    account_id: int,
    wallet_item_id: int,
) -> Optional[XboxSaleRecord]:
    """合单查询：同账号 + 同 wallet_item_id 的现有销售记录。"""
    return session.scalar(
        select(XboxSaleRecord).where(
            XboxSaleRecord.account_id == account_id,
            XboxSaleRecord.wallet_item_id == wallet_item_id,
        )
    )


def create_or_merge_sale_record(
    session: Session,
    *,
    account: XboxAccount,
    sale_date: date,
    product_name: str,
    operator_name: str,
    sale_price: Decimal,
    sale_currency: str,
    wallet_method_id: int,
    wallet_item_id: int,
    wallet_item_label: str,
    wallet_pool_id: int,
    order: Optional[XboxOrder] = None,
) -> XboxSaleRecord:
    """创建销售记录或合并到现有的（FR-06）+ 资金池入账（FR-07）。

    若同账号 + 同 wallet_item_id 已有销售记录 → 累加 sale_price + credit 差额。
    否则新建销售记录 + credit 全额。

    传入 ``order`` 时,会把订单的 sale_record_id 指向新/旧记录,
    并把订单 status 改成 converted。
    """
    pool = _validate_pool_currency(session, wallet_pool_id, sale_currency)
    sale_price = Decimal(sale_price)
    if sale_price < 0:
        raise ValueError("销售价格不能为负数")

    existing = _find_existing_sale_record(session, account.id, wallet_item_id)

    if existing is None:
        # 新建销售记录
        record = XboxSaleRecord(
            account_id=account.id,
            sale_date=sale_date,
            product_name=product_name,
            operator_name=operator_name,
            sale_price=sale_price,
            sale_currency=sale_currency,
            wallet_method_id=wallet_method_id,
            wallet_item_id=wallet_item_id,
            wallet_item_label=wallet_item_label,
            wallet_pool_id=wallet_pool_id,
        )
        session.add(record)
        session.flush()

        # credit 全额入账（除非 sale_price=0,叠加档）
        if sale_price > 0:
            tx = credit(
                session,
                wallet_pool_id,
                sale_price,
                remark=f"XBOX 销售 #{record.id} {product_name}",
            )
            record.bookkeeping_tx_id = tx.id

    else:
        # 合单：累加 sale_price + credit 差额
        if existing.sale_currency != sale_currency:
            raise ValueError(
                f"合单失败：币种不一致(已有 {existing.sale_currency},新 {sale_currency})"
            )
        if existing.wallet_pool_id != wallet_pool_id:
            raise ValueError(
                f"合单失败：资金池不一致(已有 wallet_pool_id={existing.wallet_pool_id},"
                f"新 {wallet_pool_id})"
            )
        old_price = Decimal(existing.sale_price)
        new_total = old_price + sale_price
        diff = sale_price  # 新增订单贡献的金额

        existing.sale_price = new_total
        existing.last_updated_at = china_now()
        if existing.wallet_item_label != wallet_item_label:
            existing.wallet_item_label = wallet_item_label

        # 更新 product_name 为合单后追加（保留原来 + 新订单）
        if product_name and product_name not in (existing.product_name or ""):
            existing.product_name = f"{existing.product_name}; {product_name}"

        # credit 差额到资金池
        if diff > 0:
            tx = credit(
                session,
                wallet_pool_id,
                diff,
                remark=f"XBOX 销售 #{existing.id} 合单追加 {product_name}",
            )
            # 注意：bookkeeping_tx_id 仅记最后一次（实际有多笔流水）
            existing.bookkeeping_tx_id = tx.id

        record = existing

    # 关联订单
    if order is not None:
        order.sale_record_id = record.id
        order.status = XboxOrderStatus.CONVERTED.value
        order.last_updated_at = china_now()

    session.flush()
    return record


def update_sale_record_fields(
    session: Session,
    record: XboxSaleRecord,
    *,
    sale_date: Optional[date] = None,
    product_name: Optional[str] = None,
    operator_name: Optional[str] = None,
    sale_price: Optional[Decimal] = None,
    sale_currency: Optional[str] = None,
    wallet_method_id: Optional[int] = None,
    wallet_item_id: Optional[int] = None,
    wallet_item_label: Optional[str] = None,
    wallet_pool_id: Optional[int] = None,
) -> XboxSaleRecord:
    """改销售记录字段。自动联动钱包余额（CEO Q2A + Q3A）。

    - 改 sale_price: 资金池 diff 调整
    - 改 wallet_pool_id（或 sale_currency 联动）：旧池 debit + 新池 credit
    """
    now = china_now()

    new_currency = sale_currency if sale_currency is not None else record.sale_currency
    new_pool_id = wallet_pool_id if wallet_pool_id is not None else record.wallet_pool_id
    new_price = Decimal(sale_price) if sale_price is not None else Decimal(record.sale_price)
    if new_price < 0:
        raise ValueError("销售价格不能为负数")

    pool_changed = new_pool_id != record.wallet_pool_id
    currency_changed = new_currency != record.sale_currency
    price_changed = new_price != Decimal(record.sale_price)

    # 校验新池子币种
    if pool_changed or currency_changed:
        _validate_pool_currency(session, new_pool_id, new_currency)

    # 1) 资金池变更（含 currency 变更）→ 旧池 debit 全额,新池 credit 全额
    if pool_changed or currency_changed:
        old_amount = Decimal(record.sale_price)
        if old_amount > 0:
            debit(
                session,
                record.wallet_pool_id,
                old_amount,
                remark=f"XBOX 销售 #{record.id} 切换资金池(撤旧池)",
            )
        if new_price > 0:
            tx = credit(
                session,
                new_pool_id,
                new_price,
                remark=f"XBOX 销售 #{record.id} 切换资金池(入新池)",
            )
            record.bookkeeping_tx_id = tx.id
        record.wallet_pool_id = new_pool_id
        record.sale_currency = new_currency
        record.sale_price = new_price
    elif price_changed:
        # 2) 仅价格变更 → diff 调整本池
        diff = new_price - Decimal(record.sale_price)
        if diff > 0:
            tx = credit(
                session,
                record.wallet_pool_id,
                diff,
                remark=f"XBOX 销售 #{record.id} 售价调整 +{diff}",
            )
            record.bookkeeping_tx_id = tx.id
        elif diff < 0:
            debit(
                session,
                record.wallet_pool_id,
                -diff,
                remark=f"XBOX 销售 #{record.id} 售价调整 {diff}",
            )
        record.sale_price = new_price

    # 3) 更新其他普通字段
    if sale_date is not None:
        record.sale_date = sale_date
    if product_name is not None:
        record.product_name = product_name
    if operator_name is not None:
        record.operator_name = operator_name
    if wallet_method_id is not None:
        record.wallet_method_id = wallet_method_id
    if wallet_item_id is not None:
        record.wallet_item_id = wallet_item_id
    if wallet_item_label is not None:
        record.wallet_item_label = wallet_item_label

    record.last_updated_at = now
    session.flush()
    return record


def list_sale_records(
    session: Session,
    *,
    account_id: Optional[int] = None,
    wallet_pool_id: Optional[int] = None,
) -> list[XboxSaleRecord]:
    stmt = select(XboxSaleRecord).order_by(XboxSaleRecord.id.desc())
    if account_id is not None:
        stmt = stmt.where(XboxSaleRecord.account_id == account_id)
    if wallet_pool_id is not None:
        stmt = stmt.where(XboxSaleRecord.wallet_pool_id == wallet_pool_id)
    return list(session.scalars(stmt))
