"""一次性迁移：把聚合可提现里历史合并的 IN 流水按业务日期拆分。

背景：
  PR #98 之前 ``_auto_release_aggregator`` 一次性 debit/credit,1300+ 笔订单
  合并成 1 条 IN 流水。新版按 mature_at 日期分组,但历史那 2 条合并 IN
  仍是一整笔(business_date=NULL),日汇总只能显示 release 那天一行。

  本脚本反向追溯：通过配对的 frozen OUT tx 找出当时被释放的 frozen IN 集合,
  按 ``order.confirmed_at + 7 天`` 分组求和,把原合并 IN 拆成 N 笔（每天一笔）。

  运行后聚合可提现日汇总按业务日期散开,与 PR #98 新数据口径一致。

幂等：可重复运行,已拆分(business_date 非空)的不会再处理。
"""
from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path


def _parse_dt(s: str) -> datetime:
    """SQLite TEXT → datetime,容忍带 / 不带毫秒。"""
    s = s.strip()
    if "." in s:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S.%f")
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")


def main(db_path: str = "finance.db") -> None:
    if not Path(db_path).exists():
        raise FileNotFoundError(f"DB 不存在: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        # 找各店铺
        shops = list(
            conn.execute(
                "SELECT id, name, aggregator_frozen_wallet_id, aggregator_available_wallet_id FROM taobao_shops"
            )
        )

        for shop in shops:
            frozen_wid = shop["aggregator_frozen_wallet_id"]
            avail_wid = shop["aggregator_available_wallet_id"]

            # 该店 available 钱包里 business_date 为空的 IN（历史合并数据）
            legacy_in = list(
                conn.execute(
                    """SELECT id, amount, created_at, remark FROM wallet_transactions
                       WHERE wallet_id=? AND direction='in' AND business_date IS NULL
                       ORDER BY id""",
                    (avail_wid,),
                )
            )
            print(f"[{shop['name']}] 待迁移 available IN: {len(legacy_in)} 笔")
            if not legacy_in:
                continue

            # 已被 release 的 frozen IN（mature_at NULL,仍 active）按 id 升序
            # 这些是配对源,按 id 顺序累计金额匹配各 release 批次
            all_released_frozen_in = list(
                conn.execute(
                    """SELECT t.id, t.amount, o.confirmed_at
                       FROM wallet_transactions t
                       JOIN taobao_orders o ON o.bookkeeping_tx_id = t.id
                       WHERE t.wallet_id=? AND t.direction='in' AND t.mature_at IS NULL
                       ORDER BY t.id""",
                    (frozen_wid,),
                )
            )
            cursor_idx = 0  # 在 all_released_frozen_in 里的游标

            for legacy in legacy_in:
                target_amount = Decimal(str(legacy["amount"]))
                target_id = legacy["id"]

                # 累加 frozen IN 金额直到等于 legacy.amount
                cumulative = Decimal("0")
                matched_indices: list[int] = []
                for i in range(cursor_idx, len(all_released_frozen_in)):
                    fr = all_released_frozen_in[i]
                    cumulative += Decimal(str(fr["amount"]))
                    matched_indices.append(i)
                    if cumulative == target_amount:
                        break
                else:
                    print(
                        f"  [WARN] avail IN id={target_id} amount=¥{target_amount} 找不到精确匹配"
                        f"（累计到 ¥{cumulative}）,跳过"
                    )
                    continue

                # 按 confirmed_at + 7d 分组
                groups: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
                groups_count: dict[str, int] = defaultdict(int)
                for i in matched_indices:
                    fr = all_released_frozen_in[i]
                    if fr["confirmed_at"]:
                        biz_dt = _parse_dt(fr["confirmed_at"]) + timedelta(days=7)
                        biz_day = biz_dt.date().isoformat()
                    else:
                        biz_day = "1970-01-01"  # fallback
                    groups[biz_day] += Decimal(str(fr["amount"]))
                    groups_count[biz_day] += 1

                # 推进游标到这批之后
                cursor_idx = matched_indices[-1] + 1

                print(f"  avail IN id={target_id} amount=¥{target_amount} → 拆 {len(groups)} 天:")
                for day in sorted(groups.keys()):
                    print(f"    {day}: ¥{groups[day]:.2f} ({groups_count[day]} 笔)")

                # 安全检查：分组求和应该 = 原总额
                groups_sum = sum(groups.values(), Decimal("0"))
                if groups_sum != target_amount:
                    print(f"  [ERROR] 分组求和 ¥{groups_sum} ≠ 原 ¥{target_amount},跳过")
                    continue

                # 删原合并 IN tx
                conn.execute("DELETE FROM wallet_transactions WHERE id=?", (target_id,))

                # 插 N 笔新 IN tx,各带 business_date
                base_remark = legacy["remark"] or ""
                created_at = legacy["created_at"]
                for day in sorted(groups.keys()):
                    amount_str = f"{groups[day]:.6f}"
                    new_remark = f"{base_remark} [迁移拆分:{day}]"
                    conn.execute(
                        """INSERT INTO wallet_transactions
                           (wallet_id, amount, direction, remark, created_at, business_date)
                           VALUES (?, ?, 'in', ?, ?, ?)""",
                        (avail_wid, amount_str, new_remark, created_at, day),
                    )
                print(f"  ✓ 已删原 IN id={target_id},插入 {len(groups)} 笔新 IN")

        conn.commit()
        print("\n[OK] 迁移完成,已 commit")
    except Exception as exc:
        conn.rollback()
        print(f"\n[ERROR] {exc}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
