"""聚合冻结钱包"待解冻"统计 helper。

抽出 ``calculate_pending_maturity``，让 GET /taobao/shops 与
POST /taobao/shops/{id}/aggregator/release 共享同一份计算逻辑，
避免规则漂移。

判定规则（与 release 端点完全一致）：
  - ``WalletTransaction.wallet_id == frozen_wallet_id``
  - ``direction == "in"``
  - ``mature_at IS NOT NULL AND mature_at <= now()``
  - 防御性二次过滤：仅保留仍被某 ``TaobaoOrder.bookkeeping_tx_id``
    引用的流水（剔除已被 reconcile 撤销的孤儿流水）
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.taobao import TaobaoOrder
from src.models.wallet import TransactionDirection, WalletTransaction


def calculate_pending_maturity(
    session: Session,
    frozen_wallet_id: int,
) -> tuple[Decimal, int]:
    """统计某聚合冻结钱包当前可解冻的累计金额与笔数。

    返回 ``(amount, count)``。无可解冻流水时返回 ``(Decimal("0"), 0)``。
    """
    now = datetime.now(timezone.utc)

    matured_txs = list(
        session.scalars(
            select(WalletTransaction)
            .where(
                WalletTransaction.wallet_id == frozen_wallet_id,
                WalletTransaction.direction == TransactionDirection.IN.value,
                WalletTransaction.mature_at.is_not(None),
                WalletTransaction.mature_at <= now,
            )
            .order_by(WalletTransaction.id)
        )
    )

    if not matured_txs:
        return Decimal("0"), 0

    # 防御：只算仍被某 order.bookkeeping_tx_id 引用的（说明流水未被 reconcile 撤）
    tx_ids = [tx.id for tx in matured_txs]
    active_tx_ids = set(
        session.scalars(
            select(TaobaoOrder.bookkeeping_tx_id).where(
                TaobaoOrder.bookkeeping_tx_id.in_(tx_ids)
            )
        )
    )
    active_txs = [tx for tx in matured_txs if tx.id in active_tx_ids]

    if not active_txs:
        return Decimal("0"), 0

    amount = sum((Decimal(tx.amount) for tx in active_txs), Decimal("0"))
    return amount, len(active_txs)
