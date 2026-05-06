"""一次性迁移：清理已释放但 mature_at 未清的聚合冻结流水。

背景：
  PR fix/maturity-include-today-and-idempotency 之前,_auto_release_aggregator
  完成解冻后没有清掉 IN 流水的 mature_at,导致同一批订单可被反复匹配释放。

判定方法（精确还原历史 release 时刻的 IN 集合）：
  对每个 frozen 钱包的每条 OUT 流水：
    1. OUT.created_at = 当时执行解冻的时刻
    2. 那一刻被释放的 IN = 满足 ``id < OUT.id AND mature_at <= OUT.created_at
       AND mature_at IS NOT NULL AND 仍被某 order 引用`` 的所有 IN
    3. 把这些 IN 的 mature_at 设为 None
  幂等：可重复运行,已清空 mature_at 的不会再被处理。

验证：处理后,sum(被清流水 amount) 应等于 OUT.amount（remark 也对得上"N 笔到期"）。
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select

from src.database import SessionLocal
from src.models.taobao import TaobaoOrder, TaobaoShop
from src.models.wallet import TransactionDirection, WalletTransaction


def main() -> None:
    session = SessionLocal()
    try:
        shops = list(session.scalars(select(TaobaoShop).order_by(TaobaoShop.id)))
        for shop in shops:
            frozen_wid = shop.aggregator_frozen_wallet_id

            out_txs = list(
                session.scalars(
                    select(WalletTransaction)
                    .where(
                        WalletTransaction.wallet_id == frozen_wid,
                        WalletTransaction.direction == TransactionDirection.OUT.value,
                    )
                    .order_by(WalletTransaction.id)
                )
            )
            print(f"[{shop.name}] frozen_wid={frozen_wid} OUT 流水: {len(out_txs)} 条")
            if not out_txs:
                continue

            for out_tx in out_txs:
                released_in = list(
                    session.execute(
                        select(WalletTransaction)
                        .join(TaobaoOrder, TaobaoOrder.bookkeeping_tx_id == WalletTransaction.id)
                        .where(
                            WalletTransaction.wallet_id == frozen_wid,
                            WalletTransaction.direction == TransactionDirection.IN.value,
                            WalletTransaction.mature_at.is_not(None),
                            WalletTransaction.mature_at <= out_tx.created_at,
                            WalletTransaction.id < out_tx.id,
                        )
                        .order_by(WalletTransaction.id)
                    ).scalars()
                )
                clear_sum = sum((Decimal(t.amount) for t in released_in), Decimal("0"))
                print(
                    f"  OUT#{out_tx.id} created={out_tx.created_at} amount=¥{out_tx.amount}"
                    f" → 候选 IN {len(released_in)} 笔/¥{clear_sum}"
                )
                if clear_sum != Decimal(str(out_tx.amount)):
                    print(
                        f"    ⚠ sum 不匹配 OUT.amount，跳过本 OUT 不清(避免错清)。"
                        f" 差额={Decimal(str(out_tx.amount)) - clear_sum}"
                    )
                    continue
                for tx in released_in:
                    tx.mature_at = None
                print(f"    ✓ 已清 {len(released_in)} 笔 mature_at")

        session.commit()
        print("\n[OK] 迁移完成,已 commit")
    except Exception as exc:
        session.rollback()
        print(f"\n[ERROR] {exc}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
