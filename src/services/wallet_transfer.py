"""划转单(钱包间转账) 业务服务.

Issue #129 (CEO 2026-05-18):
- 一笔划转 = 两条 wallet_transactions(一 OUT 一 IN), 通过 transfer_id 绑死
- 用户填两个金额, 系统自动算 rate = to_amount / from_amount
- from_currency / to_currency 是钱包当前币种的快照, 防钱包改名/改币种导致历史汇率失真
- 撤销: 反向冲销两条流水 + transfer.deleted_at 软删
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.wallet import (
    Currency,
    Wallet,
    WalletTransaction,
    WalletTransfer,
    credit,
    debit,
)
from src.utils.time import china_now


def _currency_value(wallet: Wallet) -> str:
    return wallet.currency.value if isinstance(wallet.currency, Currency) else wallet.currency


def _to_positive_decimal(amount: Decimal | int | float | str, field: str) -> Decimal:
    value = Decimal(str(amount))
    if value <= 0:
        raise ValueError(f"{field} 必须大于 0")
    return value


def create_transfer(
    session: Session,
    *,
    from_wallet_id: int,
    to_wallet_id: int,
    from_amount: Decimal | int | float | str,
    to_amount: Decimal | int | float | str,
    business_date: Optional[date] = None,
    operator_name: Optional[str] = None,
    note: Optional[str] = None,
) -> WalletTransfer:
    """创建划转单 + 两条关联流水.

    事务关键步骤(全部在调用方 session 内, 由路由层 commit):
    1. 校验: 两钱包都存在、非 group、非同钱包、from/to amount > 0
    2. debit from_wallet
    3. credit to_wallet
    4. 创建 WalletTransfer(rate = to / from, from/to currency 快照)
    5. 把两条 tx 的 transfer_id 更新为 transfer.id
    6. flush + 返回
    """
    if from_wallet_id == to_wallet_id:
        raise ValueError("不能划转到同一个钱包")

    from_amount_dec = _to_positive_decimal(from_amount, "出账金额")
    to_amount_dec = _to_positive_decimal(to_amount, "入账金额")

    from_wallet = session.get(Wallet, from_wallet_id)
    if from_wallet is None:
        raise ValueError("出账钱包不存在")
    to_wallet = session.get(Wallet, to_wallet_id)
    if to_wallet is None:
        raise ValueError("入账钱包不存在")

    if from_wallet.is_group:
        raise ValueError("出账钱包是分组节点, 不能记账")
    if to_wallet.is_group:
        raise ValueError("入账钱包是分组节点, 不能记账")
    if from_wallet.deleted_at is not None:
        raise ValueError("出账钱包已删除")
    if to_wallet.deleted_at is not None:
        raise ValueError("入账钱包已删除")

    from_currency = _currency_value(from_wallet)
    to_currency = _currency_value(to_wallet)
    # 汇率精度 8 位, quantize 防止 to_amount/from_amount 出现长尾小数
    rate = (to_amount_dec / from_amount_dec).quantize(Decimal("0.00000001"))

    remark = f"[划转] {from_wallet.name}→{to_wallet.name} @ {rate}"

    # debit 会抛 ValueError("insufficient wallet balance"), 由调用方 catch
    out_tx = debit(
        session,
        from_wallet_id,
        from_amount_dec,
        remark=remark,
        operator_name=operator_name,
    )
    in_tx = credit(
        session,
        to_wallet_id,
        to_amount_dec,
        remark=remark,
        business_date=business_date,
        operator_name=operator_name,
    )

    transfer = WalletTransfer(
        from_wallet_id=from_wallet_id,
        to_wallet_id=to_wallet_id,
        from_amount=from_amount_dec,
        to_amount=to_amount_dec,
        rate=rate,
        from_currency=from_currency,
        to_currency=to_currency,
        business_date=business_date,
        operator_name=operator_name,
        note=note,
    )
    session.add(transfer)
    session.flush()

    # 把两条 tx 的 transfer_id 绑定到新建的 transfer
    out_tx.transfer_id = transfer.id
    in_tx.transfer_id = transfer.id
    session.flush()

    return transfer


def get_transfer(session: Session, transfer_id: int) -> Optional[WalletTransfer]:
    return session.get(WalletTransfer, transfer_id)


def list_transfers(
    session: Session,
    *,
    from_wallet_id: Optional[int] = None,
    to_wallet_id: Optional[int] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    operator_name: Optional[str] = None,
    include_deleted: bool = False,
) -> list[WalletTransfer]:
    """列表 + 多条件筛选.

    日期筛选用 business_date(没填则不参与该条件; 调用方可改为 created_at 但
    业务上 CEO 关心的是"这笔划转算哪天的钱", 应该是 business_date).
    """
    stmt = select(WalletTransfer)
    if not include_deleted:
        stmt = stmt.where(WalletTransfer.deleted_at.is_(None))
    if from_wallet_id is not None:
        stmt = stmt.where(WalletTransfer.from_wallet_id == from_wallet_id)
    if to_wallet_id is not None:
        stmt = stmt.where(WalletTransfer.to_wallet_id == to_wallet_id)
    if from_date is not None:
        stmt = stmt.where(WalletTransfer.business_date >= from_date)
    if to_date is not None:
        stmt = stmt.where(WalletTransfer.business_date <= to_date)
    if operator_name:
        stmt = stmt.where(WalletTransfer.operator_name == operator_name)
    stmt = stmt.order_by(WalletTransfer.id.desc())
    return list(session.scalars(stmt))


def find_transfer_transactions(
    session: Session, transfer_id: int
) -> list[WalletTransaction]:
    """查这笔划转关联的所有 wallet_transactions(应该是 2 条: OUT + IN).

    撤销时也包含为了撤销而新建的反向冲销流水, 这是有意的: 让"流水
    透明"——撤销也是历史的一部分.
    """
    return list(
        session.scalars(
            select(WalletTransaction)
            .where(WalletTransaction.transfer_id == transfer_id)
            .order_by(WalletTransaction.id)
        )
    )


def cancel_transfer(session: Session, transfer_id: int) -> WalletTransfer:
    """撤销划转: 反向冲销 + 软删 transfer.

    校验:
    - transfer 存在且未被撤销
    - to_wallet 当前余额够不够 to_amount(否则会变负余额, 拒绝)
    - to_wallet / from_wallet 不能是 group / 已删除

    操作:
    - to_wallet debit (to_amount)
    - from_wallet credit (from_amount)
    - 两条新流水也挂同一个 transfer_id, remark 标 [撤销划转 #N]
    - transfer.deleted_at = china_now()
    """
    transfer = session.get(WalletTransfer, transfer_id)
    if transfer is None:
        raise ValueError("划转单不存在")
    if transfer.deleted_at is not None:
        raise ValueError("划转单已撤销")

    from_wallet = session.get(Wallet, transfer.from_wallet_id)
    to_wallet = session.get(Wallet, transfer.to_wallet_id)
    if from_wallet is None or to_wallet is None:
        raise ValueError("关联钱包已删除, 无法撤销")
    if from_wallet.deleted_at is not None or to_wallet.deleted_at is not None:
        raise ValueError("关联钱包已删除, 无法撤销")
    if from_wallet.is_group or to_wallet.is_group:
        raise ValueError("关联钱包已变为分组, 无法撤销")

    # 反向冲销: 先把入账的钱扣回去, 再把出账的钱补回来
    # debit 会做余额校验, 不够时抛 ValueError("insufficient wallet balance")
    remark = f"[撤销划转 #{transfer.id}] {from_wallet.name}←{to_wallet.name}"
    reverse_out = debit(
        session,
        to_wallet.id,
        Decimal(transfer.to_amount),
        remark=remark,
        operator_name=transfer.operator_name,
    )
    reverse_in = credit(
        session,
        from_wallet.id,
        Decimal(transfer.from_amount),
        remark=remark,
        operator_name=transfer.operator_name,
    )
    # 撤销冲销的两条流水也挂同一个 transfer_id, 这样查流水时能完整看到一笔
    # 划转的全过程(原始 OUT + 原始 IN + 撤销 OUT + 撤销 IN)
    reverse_out.transfer_id = transfer.id
    reverse_in.transfer_id = transfer.id

    transfer.deleted_at = china_now()
    session.flush()
    return transfer
