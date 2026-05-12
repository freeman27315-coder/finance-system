"""XBOX Playwright 首次登录脚本 (CEO 2026-05-12 PR D)。

用途:
- Playwright 启动的 Chromium 是独立实例,cookies 跟 CEO 平时用的浏览器不通。
- 第一次跑真实抓取前,需要在 Playwright 浏览器里手动登录一次,把"信任设备"
  cookies 写到 user_data_dir。之后所有真实抓取就能自动复用这些 cookies。

用法:
    cd 仓库根目录
    python scripts/xbox_first_run_login.py <account_id>

操作流程:
1. 脚本会启动一个 headed 浏览器(看得见)
2. 自动填邮箱密码 + 提交
3. 弹 2FA 时,你手动用邮箱/手机完成验证
4. 看到 "Stay signed in?" 点 Yes(让 cookies 持久化)
5. 进入 https://account.microsoft.com/billing/orders 页面后,关掉浏览器即可
6. cookies 写入 .playwright-user-data/xbox/
7. 后续 trigger_sync 会自动复用,headless 跑成功
"""
from __future__ import annotations

import os
import sys

# 强制 headed
os.environ["XBOX_PLAYWRIGHT_HEADLESS"] = "false"

from src import database
from src.models.xbox import XboxAccount
from src.services.xbox_account import reveal_password
from src.services.xbox_playwright import first_run_login


def main() -> int:
    if len(sys.argv) != 2:
        print("用法: python scripts/xbox_first_run_login.py <account_id>")
        return 1

    try:
        account_id = int(sys.argv[1])
    except ValueError:
        print(f"账号 id 必须是整数, 实际: {sys.argv[1]}")
        return 1

    database.init_db()
    db = database.SessionLocal()
    try:
        account = db.get(XboxAccount, account_id)
        if account is None:
            print(f"账号 {account_id} 不存在")
            return 1
        if not account.login_email or not account.password_enc:
            print(f"账号 {account_id} 未设置 login_email / password,无法登录")
            return 1
        password_plain = reveal_password(account)
        print(f"使用账号: {account.login_email}")
        result = first_run_login(account.login_email, password_plain)
        print(result)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
