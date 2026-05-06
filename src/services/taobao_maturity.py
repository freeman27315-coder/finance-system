"""聚合冻结钱包"待解冻"统计 helper。

让 GET /taobao/shops 显示 ``aggregator_matured_amount`` 与
导入末尾 ``_auto_release_aggregator`` 共享同一份"成熟筛选"逻辑。

判定规则（CEO 业务口径,2026-05-06 修订）：
  - ``WalletTransaction.wallet_id == frozen_wallet_id``
  - ``direction == "in"``
  - ``mature_at IS NOT NULL`` 且 ``mature_at < 明天 00:00:00``
    （含今天任何时刻才到期的订单 —— 4/28 14:02 确认 → mature_at 5/5 14:02，
     5/5 早晨查询时已计入"可提现"，与千牛后台口径一致）
  - 防御性二次过滤：仅保留仍被某 ``TaobaoOrder.bookkeeping_tx_id``
    引用的流水（剔除已被 reconcile 撤销的孤儿流水）

时区：mature_at 为 naive China 本地（写入时 ``confirmed_at + 7d``,
confirmed_at 来自 Excel 中国本地时间）。``datetime.now()`` 同样取服务器本地
（CEO 机器在中国时区）→ naive vs naive 比较安全。
"""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.taobao import TaobaoOrder
from src.models.wallet import TransactionDirection, WalletTransaction
from src.utils.time import china_now


def _today_cutoff() -> datetime:
    """返回明天 00:00:00（中国时间 naive）—— mature_at < cutoff 即视为今天或之前到期。"""
    now = china_now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return today_start + timedelta(days=1)


def matured_active_txs(
    session: Session,
    frozen_wallet_id: int,
) -> list[WalletTransaction]:
    """共享 helper：返回当前应被解冻的 active IN 流水列表。

    - 满足 ``mature_at < 明天 0:00`` 且 ``mature_at IS NOT NULL``
    - 仍被某 ``TaobaoOrder.bookkeeping_tx_id`` 引用
    """
    cutoff = _today_cutoff()

    matured_txs = list(
        session.scalars(
            select(WalletTransaction)
            .where(
                WalletTransaction.wallet_id == frozen_wallet_id,
                WalletTransaction.direction == TransactionDirection.IN.value,
                WalletTransaction.mature_at.is_not(None),
                WalletTransaction.mature_at < cutoff,
            )
            .order_by(WalletTransaction.id)
        )
    )

    if not matured_txs:
        return []

    tx_ids = [tx.id for tx in matured_txs]
    active_tx_ids = set(
        session.scalars(
            select(TaobaoOrder.bookkeeping_tx_id).where(
                TaobaoOrder.bookkeeping_tx_id.in_(tx_ids)
            )
        )
    )
    return [tx for tx in matured_txs if tx.id in active_tx_ids]


def calculate_pending_maturity(
    session: Session,
    frozen_wallet_id: int,
) -> tuple[Decimal, int]:
    """统计某聚合冻结钱包当前可解冻的累计金额与笔数。

    返回 ``(amount, count)``。无可解冻流水时返回 ``(Decimal("0"), 0)``。
    """
    active_txs = matured_active_txs(session, frozen_wallet_id)
    if not active_txs:
        return Decimal("0"), 0
    amount = sum((Decimal(tx.amount) for tx in active_txs), Decimal("0"))
    return amount, len(active_txs)
