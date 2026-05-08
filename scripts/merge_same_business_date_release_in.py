"""一次性清理：合并聚合可提现里同 business_date 的多笔 release IN 流水。

背景：
  历史上多次 _auto_release_aggregator 操作各自把订单按 business_date 拆分。
  ``scripts/migrate_available_business_date.py`` 对每次 release 独立拆,
  没合并跨 release 的同 business_date 流水。结果：流水抽屉里同一天可能
  出现 2 条 release IN（来自不同 release 操作）,不直观。

  本脚本把同一 wallet × business_date × direction='in' 的多笔合并成 1 笔：
  - 保留最早 id（保持时序）
  - amount = 同组求和
  - remark 标记"合并自 N 笔"
  - 删除其他

幂等：可重复运行,已合并(每个组只剩 1 笔)的不会再处理。
"""
from __future__ import annotations

import sqlite3
from collections import defaultdict
from decimal import Decimal
from pathlib import Path


def main(db_path: str = "finance.db") -> None:
    if not Path(db_path).exists():
        raise FileNotFoundError(f"DB 不存在: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        # 找所有店铺的 aggregator_available 钱包
        avail_wids = [
            row["aggregator_available_wallet_id"]
            for row in conn.execute(
                "SELECT aggregator_available_wallet_id FROM taobao_shops"
            )
        ]

        for wid in avail_wids:
            # 同 business_date 出现多笔的 IN 流水
            groups = list(
                conn.execute(
                    """SELECT business_date, COUNT(*) AS cnt, SUM(amount) AS total
                       FROM wallet_transactions
                       WHERE wallet_id=? AND direction='in' AND business_date IS NOT NULL
                       GROUP BY business_date HAVING cnt > 1
                       ORDER BY business_date""",
                    (wid,),
                )
            )
            if not groups:
                print(f"[wallet {wid}] 没有需要合并的同日期组")
                continue

            print(f"[wallet {wid}] 待合并 {len(groups)} 个日期组：")
            for g in groups:
                print(f"  {g['business_date']}: {g['cnt']} 笔 → 合计 ¥{Decimal(str(g['total'])):.2f}")

                # 取该组的所有 IN 流水
                txs = list(
                    conn.execute(
                        """SELECT id, amount FROM wallet_transactions
                           WHERE wallet_id=? AND direction='in' AND business_date=?
                           ORDER BY id""",
                        (wid, g["business_date"]),
                    )
                )
                if len(txs) <= 1:
                    continue

                first_id = txs[0]["id"]
                merge_count = len(txs)
                total_amount = Decimal(str(g["total"]))

                # 更新最早那笔为合并后的金额 + 改 remark
                new_remark = f"导入自动解冻（{merge_count} 次 release 合并到 {g['business_date']}）"
                conn.execute(
                    """UPDATE wallet_transactions
                       SET amount=?, remark=?
                       WHERE id=?""",
                    (f"{total_amount:.6f}", new_remark, first_id),
                )

                # 删除其他笔
                other_ids = [tx["id"] for tx in txs[1:]]
                conn.execute(
                    f"DELETE FROM wallet_transactions WHERE id IN ({','.join('?' * len(other_ids))})",
                    other_ids,
                )

                print(f"    ✓ 保留 id={first_id} (amount=¥{total_amount}),删 {len(other_ids)} 笔")

        conn.commit()
        print("\n[OK] 合并完成,已 commit")
    except Exception as exc:
        conn.rollback()
        print(f"\n[ERROR] {exc}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
