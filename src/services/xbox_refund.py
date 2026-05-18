"""XBOX 退款单业务服务(Issue #130 / CEO 2026-05-18)。

业务规则:
- 一笔退款 = 两条 wallet_transactions(实际钱包 OUT + 理论钱包 OUT)
- 销售记录从 status='active' → 'refunded',refund_id 指向新建的退款单
- 只支持全额退(refund_amount = sale_record.sale_price)
- 退款不动 XBOX 账号状态(账号未被使用,账号回收由客服系统处理)
- 撤销: 反向 credit 两个钱包 + 销售记录改回 active + 硬删 XboxRefund(因 UNIQUE 约束)

关键技术决定:
- 理论钱包(XBOX_SALES_LEDGER 类型)允许负余额(对账占位符,不代表真实资金).
  debit() 函数现有逻辑只对 VENDOR 网开一面,XBOX_SALES_LEDGER 没特例.
- 为了不破坏 debit() 的通用语义(改它会影响所有用了它的功能),这里实现
  ``_force_debit_no_balance_check()`` 内部 helper, 在退款服务里直接操作
  wallet.balance + 手动建 WalletTransaction,跳过余额校验.
- 实际钱包仍然走标准 debit()(有余额校验,退款时实际钱包应该够,否则报错让人工处理).
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
    WalletType,
    debit,
)
from src.models.xbox import (
    XboxChangeLog,
    XboxRefund,
    XboxSaleRecord,
    XboxSaleRecordStatus,
)
from src.utils.time import china_now


# -------- 内部 helper --------


def _force_debit_no_balance_check(
    session: Session,
    wallet_id: int,
    amount: Decimal,
    *,
    remark: Optional[str] = None,
    operator_name: Optional[str] = None,
) -> WalletTransaction:
    """绕过 debit() 的余额校验, 直接扣钱 + 写 OUT 流水.

    用于理论钱包(XBOX_SALES_LEDGER): 这种钱包是对账占位符, 余额可以为负
    (例如 30 天总销售 100 + 退款 120 → 余额 -20, 不是 bug 是业务正常状态).
    """
    if amount <= 0:
        raise ValueError("amount must be greater than zero")
    wallet = session.get(Wallet, wallet_id)
    if wallet is None:
        raise ValueError(f"wallet {wallet_id} does not exist")
    wallet.balance = Decimal(wallet.balance) - amount
    tx = WalletTransaction(
        wallet_id=wallet_id,
        amount=amount,
        direction=TransactionDirection.OUT,
        remark=remark,
        operator_name=operator_name,
    )
    session.add(tx)
    session.flush()
    return tx


def _force_credit_no_balance_check(
    session: Session,
    wallet_id: int,
    amount: Decimal,
    *,
    remark: Optional[str] = None,
    operator_name: Optional[str] = None,
) -> WalletTransaction:
    """理论钱包反向冲销时用 — 同样绕过常规 credit (我们要 OUT 反向, 还要不动 mature_at).

    其实标准 credit() 也能用, 这里为了和 _force_debit 对称, 直接写一份.
    """
    if amount <= 0:
        raise ValueError("amount must be greater than zero")
    wallet = session.get(Wallet, wallet_id)
    if wallet is None:
        raise ValueError(f"wallet {wallet_id} does not exist")
    wallet.balance = Decimal(wallet.balance) + amount
    tx = WalletTransaction(
        wallet_id=wallet_id,
        amount=amount,
        direction=TransactionDirection.IN,
        remark=remark,
        operator_name=operator_name,
    )
    session.add(tx)
    session.flush()
    return tx


def _log_change(
    session: Session,
    entity_type: str,
    entity_id: int,
    action: str,
    detail: str,
    operator: str = "manual",
) -> None:
    """写一条 XBOX 变更日志(action='refunded' / 'refund_cancelled')."""
    log = XboxChangeLog(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        detail=detail,
        operator=operator,
    )
    session.add(log)
    session.flush()


# -------- 公开服务 --------


def create_refund(
    session: Session,
    *,
    sale_record_id: int,
    actual_wallet_id: int,
    business_date: Optional[date] = None,
    operator_name: Optional[str] = None,
    note: Optional[str] = None,
) -> XboxRefund:
    """创建退款单(全额退,关联原销售记录)。

    事务关键步骤(全部在调用方 session 内, 由路由层 commit):
    1. 校验: sale_record 存在且 status=active、actual_wallet 存在且非 group
    2. 取 sale_price / sale_currency / wallet_pool_id(=theoretical_wallet)
    3. debit(actual_wallet, sale_price) — 普通钱包, 走标准 debit(有余额校验)
    4. force_debit(theoretical_wallet, sale_price) — XBOX_SALES_LEDGER, 跳过余额校验
    5. 建 XboxRefund 记录, 带两条 tx_id
    6. sale_record.status='refunded' / refunded_at=china_now() / refund_id=新 id
    7. 写 XboxChangeLog: entity_type='sale_record', action='refunded'
    """
    sale_record = session.get(XboxSaleRecord, sale_record_id)
    if sale_record is None:
        raise ValueError(f"销售记录 {sale_record_id} 不存在")
    if sale_record.status != XboxSaleRecordStatus.ACTIVE.value:
        raise ValueError(f"销售记录 #{sale_record_id} 状态为 {sale_record.status}, 不能退款")

    actual_wallet = session.get(Wallet, actual_wallet_id)
    if actual_wallet is None:
        raise ValueError(f"实际退款钱包 {actual_wallet_id} 不存在")
    if actual_wallet.is_group:
        raise ValueError("实际退款钱包是分组节点, 不能记账")
    if actual_wallet.deleted_at is not None:
        raise ValueError("实际退款钱包已删除")

    theoretical_wallet_id = sale_record.wallet_pool_id
    theoretical_wallet = session.get(Wallet, theoretical_wallet_id)
    if theoretical_wallet is None:
        raise ValueError(f"理论钱包(原销售记录资金池 {theoretical_wallet_id}) 不存在")

    refund_amount = Decimal(sale_record.sale_price)
    refund_currency = sale_record.sale_currency
    if refund_amount <= 0:
        raise ValueError("销售记录金额为 0, 无可退款金额")

    # 实际钱包: 走标准 debit (有余额校验). 退款时实际钱包应该够;
    # 不够说明数据有问题, 让用户人工处理(可能要先充钱进来).
    actual_tx = debit(
        session,
        actual_wallet_id,
        refund_amount,
        remark=f"[退款] 销售记录 #{sale_record_id}",
        operator_name=operator_name,
    )

    # 理论钱包: 跳过余额校验(XBOX_SALES_LEDGER 允许负余额)
    theoretical_tx = _force_debit_no_balance_check(
        session,
        theoretical_wallet_id,
        refund_amount,
        remark=f"[退款] 销售记录 #{sale_record_id}",
        operator_name=operator_name,
    )

    refund = XboxRefund(
        original_sale_record_id=sale_record_id,
        refund_amount=refund_amount,
        refund_currency=refund_currency,
        actual_wallet_id=actual_wallet_id,
        theoretical_wallet_id=theoretical_wallet_id,
        business_date=business_date,
        operator_name=operator_name,
        note=note,
        actual_bookkeeping_tx_id=actual_tx.id,
        theoretical_bookkeeping_tx_id=theoretical_tx.id,
    )
    session.add(refund)
    session.flush()

    # 销售记录 → refunded
    sale_record.status = XboxSaleRecordStatus.REFUNDED.value
    sale_record.refunded_at = china_now()
    sale_record.refund_id = refund.id
    sale_record.last_updated_at = china_now()

    _log_change(
        session,
        "sale_record",
        sale_record_id,
        "refunded",
        f"退款 #{refund.id} → 实际钱包#{actual_wallet_id} ({actual_wallet.name}) "
        f"金额 {refund_amount} {refund_currency}",
        operator=operator_name or "manual",
    )

    session.flush()
    return refund


def get_refund(session: Session, refund_id: int) -> Optional[XboxRefund]:
    return session.get(XboxRefund, refund_id)


def list_refunds(
    session: Session,
    *,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    actual_wallet_id: Optional[int] = None,
    operator_name: Optional[str] = None,
) -> list[XboxRefund]:
    """列退款单, 支持筛选: 日期范围(按 business_date 优先, 没填则按 created_at)、
    实际钱包、操作人.
    """
    from datetime import datetime, timedelta

    from sqlalchemy import and_, or_

    stmt = select(XboxRefund)
    if actual_wallet_id is not None:
        stmt = stmt.where(XboxRefund.actual_wallet_id == actual_wallet_id)
    if operator_name:
        stmt = stmt.where(XboxRefund.operator_name == operator_name)
    if from_date is not None:
        # business_date >= from_date OR (business_date IS NULL AND created_at >= from_date 00:00)
        from_dt = datetime.combine(from_date, datetime.min.time())
        stmt = stmt.where(
            or_(
                XboxRefund.business_date >= from_date,
                and_(
                    XboxRefund.business_date.is_(None),
                    XboxRefund.created_at >= from_dt,
                ),
            )
        )
    if to_date is not None:
        to_dt = datetime.combine(to_date, datetime.min.time()) + timedelta(days=1)
        stmt = stmt.where(
            or_(
                XboxRefund.business_date <= to_date,
                and_(
                    XboxRefund.business_date.is_(None),
                    XboxRefund.created_at < to_dt,
                ),
            )
        )
    stmt = stmt.order_by(XboxRefund.id.desc())
    return list(session.scalars(stmt))


def cancel_refund(session: Session, refund_id: int) -> XboxRefund:
    """撤销退款: 反向 credit 两个钱包 + 销售记录改回 active + 硬删 XboxRefund.

    校验:
    - refund 存在
    - 实际钱包当前余额够不够加回(理论上 credit 不会失败, 这里仅校验钱包存在/非删除)
    - 销售记录还在(理论上一定在, 防御性)

    操作:
    - 实际钱包 credit (refund_amount)
    - 理论钱包 force_credit (refund_amount) — 与 debit 对称
    - sale_record.status='active', refund_id=NULL, refunded_at=NULL
    - 硬删 XboxRefund(因为 original_sale_record_id UNIQUE, 留着 deleted_at 软删
      会让"同一销售记录再次退款"建第二条 refund 时违反 UNIQUE 约束)
    - 写 XboxChangeLog action='refund_cancelled'
    """
    refund = session.get(XboxRefund, refund_id)
    if refund is None:
        raise ValueError(f"退款单 {refund_id} 不存在")

    actual_wallet = session.get(Wallet, refund.actual_wallet_id)
    if actual_wallet is None:
        raise ValueError("退款单关联的实际钱包已删除, 无法撤销")
    if actual_wallet.deleted_at is not None:
        raise ValueError("退款单关联的实际钱包已删除, 无法撤销")
    if actual_wallet.is_group:
        raise ValueError("退款单关联的实际钱包已变为分组, 无法撤销")

    theoretical_wallet = session.get(Wallet, refund.theoretical_wallet_id)
    if theoretical_wallet is None:
        raise ValueError("退款单关联的理论钱包已删除, 无法撤销")

    sale_record = session.get(XboxSaleRecord, refund.original_sale_record_id)
    if sale_record is None:
        raise ValueError("退款单关联的销售记录已被删除, 无法撤销")

    refund_amount = Decimal(refund.refund_amount)
    remark = f"[撤销退款 #{refund.id}] 销售记录 #{refund.original_sale_record_id}"

    # 实际钱包 credit 回去 (从 _force_credit, 不依赖标准 credit 的 mature_at 逻辑)
    _force_credit_no_balance_check(
        session,
        refund.actual_wallet_id,
        refund_amount,
        remark=remark,
        operator_name=refund.operator_name,
    )
    # 理论钱包 credit 回去 (跳过校验, 和退款时对称)
    _force_credit_no_balance_check(
        session,
        refund.theoretical_wallet_id,
        refund_amount,
        remark=remark,
        operator_name=refund.operator_name,
    )

    # 销售记录改回 active
    sale_record.status = XboxSaleRecordStatus.ACTIVE.value
    sale_record.refunded_at = None
    sale_record.refund_id = None
    sale_record.last_updated_at = china_now()

    _log_change(
        session,
        "sale_record",
        refund.original_sale_record_id,
        "refund_cancelled",
        f"撤销退款 #{refund.id} (实际钱包#{refund.actual_wallet_id} {actual_wallet.name} "
        f"金额 {refund_amount} {refund.refund_currency})",
        operator=refund.operator_name or "manual",
    )

    # 硬删退款单
    session.delete(refund)
    session.flush()
    return refund
