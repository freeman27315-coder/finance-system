"""一次性迁移：把历史 UTC 时间戳 +8h 改成中国时间。

背景：
  PR chore/all-times-china 之前,SQLite ``server_default=func.now()`` 写的是
  ``CURRENT_TIMESTAMP``（UTC,长度 19,无毫秒）。这与 Python 写入的 China naive
  （长度 26,带毫秒）混存,导致同一表 created_at 列上存在 8 小时跳变。

PR 后所有写入都用 ``china_now()``（长度 26,毫秒,中国本地）。
本脚本把存量长度=19 的值 +8h 转成长度=26 的中国时间。

判定方法（精确）：
  对每个目标列：
    - WHERE length(col) = 19   → 旧 UTC,执行 col = strftime('%Y-%m-%d %H:%M:%f000', datetime(col, '+8 hours'))
    - WHERE length(col) = 26   → 已是中国,跳过

幂等：可重复运行,不会重复 +8h（只看长度 19 的）。

迁移目标列：
  - wallets.created_at        (server_default 写的 UTC)
  - wallets.deleted_at        (assets.py 老代码用 func.now() 写的 UTC,新代码已改 china_now)
  - wallet_transactions.created_at
  - taobao_shops.created_at
  - taobao_orders.recorded_at  (server_default 写的 UTC)

不动：
  - taobao_orders.last_synced_at  (Python 写的,长度 26,已是中国)
  - 所有 Excel 源时间(shipped_at/confirmed_at/received_at): 已是中国
  - WalletTransaction.mature_at: 已是中国
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

TARGETS = [
    ("wallets", "created_at"),
    ("wallets", "deleted_at"),
    ("wallet_transactions", "created_at"),
    ("taobao_shops", "created_at"),
    ("taobao_orders", "recorded_at"),
]


def main(db_path: str = "finance.db") -> None:
    if not Path(db_path).exists():
        raise FileNotFoundError(f"DB 文件不存在: {db_path}")

    conn = sqlite3.connect(db_path)
    try:
        for table, col in TARGETS:
            # 先看有多少行需要迁移
            count = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {col} IS NOT NULL AND length({col}) = 19"
            ).fetchone()[0]

            if count == 0:
                print(f"[{table}.{col}] 无 UTC 长度=19 的行,跳过")
                continue

            sample = conn.execute(
                f"SELECT {col} FROM {table} WHERE length({col}) = 19 LIMIT 1"
            ).fetchone()
            print(f"[{table}.{col}] {count} 行待 +8h，旧样本: {sample[0]}")

            # +8h 并补足毫秒位 → 标准化为长度 26
            conn.execute(
                f"""
                UPDATE {table}
                SET {col} = strftime('%Y-%m-%d %H:%M:%f000', datetime({col}, '+8 hours'))
                WHERE {col} IS NOT NULL AND length({col}) = 19
                """
            )

            new_sample = conn.execute(
                f"SELECT {col} FROM {table} WHERE rowid IN (SELECT rowid FROM {table} ORDER BY rowid LIMIT 1)"
            ).fetchone()
            print(f"  ✓ 已 +8h，新样本: {new_sample[0]}")

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
