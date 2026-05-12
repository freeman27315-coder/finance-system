"""验证真实抓取: 用 cookies(headless)拉账号 4 的微软订单。

CEO 2026-05-12: first_run_login 已让 user_data_dir 拿到 cookies,
这步是 headless 模式确认 cookies 有效 + 解析订单字段正确。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def _load_dotenv() -> None:
    env_path = _PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, _, v = s.partition("=")
        k, v = k.strip(), v.strip()
        if k and k not in os.environ:
            os.environ[k] = v
_load_dotenv()

from src import database
from src.models.xbox import XboxAccount
from src.services.xbox_playwright import fetch_microsoft_orders_real


def main() -> int:
    if len(sys.argv) != 2:
        print("用法: python scripts/xbox_test_real_sync.py <account_id>")
        return 1
    account_id = int(sys.argv[1])

    # 先 headed 看到浏览器(方便调试) - 后续可改 true
    os.environ["XBOX_PLAYWRIGHT_HEADLESS"] = "false"

    database.init_db()
    db = database.SessionLocal()
    try:
        account = db.get(XboxAccount, account_id)
        if account is None:
            print(f"账号 {account_id} 不存在")
            return 1

        print(f"开始抓取账号 {account.account_no or account.name} 的订单...")
        result = fetch_microsoft_orders_real(account, count=20)

        if not result.success:
            print(f"❌ 抓取失败: {result.failure_category} - {result.failure_message}")
            return 1

        print(f"✓ 抓取成功! 共 {len(result.orders)} 单")
        print()
        for i, o in enumerate(result.orders, 1):
            print(f"#{i}  订单号={o.order_no}  金额={o.amount_local} {o.currency_local}  时间={o.order_at}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
