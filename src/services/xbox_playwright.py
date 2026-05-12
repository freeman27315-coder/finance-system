"""真实 Microsoft 订单抓取 (Playwright + Chromium)。

CEO 2026-05-12 决策: Q1-A Playwright / Q2-B 用 user_data_dir 持久化登录态 /
Q3 截图已对照 / Q4 直接上真实抓取(不再 mock)。

工作原理:
1. 用 `launch_persistent_context(user_data_dir=...)` 启动 Chromium,cookies 持久化
2. 访问 https://account.microsoft.com/billing/orders
3. 检测 URL:
   - 进了订单页 → 已登录,直接抓
   - 重定向到 login.live.com → 需要登录
4. 登录流程: 填邮箱 → 下一步 → 填密码 → 提交
   - 出现 2FA 选项页 → 抛 verification_required(让 CEO 手动完成)
   - 出现 "Stay signed in?" → 点 Yes 保持登录
5. 订单页解析(参考 CEO 2026-05-12 截图):
   每个订单卡片格式:
   - "May 11, 2026 | Order number 8035392088"
   - 商品名 (h?): "80 Robux"
   - 价格: "USD$0.99" 或 "GBP£0.99"
   - 状态: "Completed"

时间精度: Microsoft 订单页面只显示到天(没时分秒)。
解析时把时间设为当天 12:00:00 中国时区(避免日期边界 + 满足 datetime 类型)。
如果详情页有更精确时间, 后续补丁迭代。

环境变量:
- XBOX_PLAYWRIGHT_USER_DATA_DIR (默认 ./.playwright-user-data/xbox)
- XBOX_PLAYWRIGHT_HEADLESS (默认 true; 首次手动登录时设 false 看着完成 2FA)
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Optional

from playwright.sync_api import (
    Page,
    Playwright,
    Browser,
    BrowserContext,
    TimeoutError as PlaywrightTimeout,
    sync_playwright,
)

from src.models.xbox import XboxAccount
from src.utils.crypto import decrypt_password
from src.utils.time import china_now

# ---------------------------------------------------------------------------
# 类型: 复用 xbox_sync 里的 dataclass 避免循环引用
# ---------------------------------------------------------------------------

from src.services.xbox_sync import FetchedBalance, FetchedOrder, FetchResult


_ORDERS_URL = "https://account.microsoft.com/billing/orders"
_LOGIN_URL_PREFIX = "https://login.live.com/"

# 解析正则
_ORDER_NO_RE = re.compile(r"Order\s+number\s+(\d+)")
_DATE_RE = re.compile(
    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2}),\s+(\d{4})"
)
_PRICE_RE = re.compile(r"(USD\$|GBP£|\$|£)([\d,]+\.\d{1,2})")
_MONTH_NAMES = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------


def _user_data_dir() -> Path:
    raw = os.environ.get(
        "XBOX_PLAYWRIGHT_USER_DATA_DIR",
        str(Path.cwd() / ".playwright-user-data" / "xbox"),
    )
    p = Path(raw)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _is_headless() -> bool:
    val = os.environ.get("XBOX_PLAYWRIGHT_HEADLESS", "true").lower()
    return val in {"1", "true", "yes"}


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------


def fetch_microsoft_orders_real(
    account: XboxAccount,
    count: int,
) -> FetchResult:
    """用 Playwright 真实抓取 Microsoft 订单 (CEO 2026-05-12 PR D)。

    返回的 ``FetchResult`` 结构与 stub 完全一致(可直接替换 trigger_sync 调用)。
    """
    if not account.login_email or not account.password_enc:
        return FetchResult(
            success=False,
            orders=[],
            balance=None,
            failure_category="password_error",
            failure_message="账号未设置登录邮箱或密码",
        )

    try:
        password_plain = decrypt_password(account.password_enc)
    except Exception as exc:
        return FetchResult(
            success=False,
            orders=[],
            balance=None,
            failure_category="password_error",
            failure_message=f"密码解密失败: {exc}",
        )

    try:
        with sync_playwright() as p:
            ctx = _launch_context(p)
            try:
                page = ctx.pages[0] if ctx.pages else ctx.new_page()
                result = _do_fetch(page, account.login_email, password_plain, count)
            finally:
                try:
                    ctx.close()
                except Exception:
                    pass
        return result
    except Exception as exc:  # 网络断 / Chromium 启动失败 / 未预料异常
        return FetchResult(
            success=False,
            orders=[],
            balance=None,
            failure_category="unknown",
            failure_message=f"Playwright 抓取异常: {exc}",
        )


# ---------------------------------------------------------------------------
# 流程内部
# ---------------------------------------------------------------------------


def _launch_context(p: Playwright) -> BrowserContext:
    """启动持久化 Chromium 上下文(cookies 存在 user_data_dir)。"""
    return p.chromium.launch_persistent_context(
        user_data_dir=str(_user_data_dir()),
        headless=_is_headless(),
        args=[
            "--disable-blink-features=AutomationControlled",  # 降低 bot 特征
        ],
        viewport={"width": 1280, "height": 800},
        locale="en-US",
    )


def _do_fetch(
    page: Page,
    login_email: str,
    password_plain: str,
    count: int,
) -> FetchResult:
    """登录 + 拉订单。"""
    # 访问订单页 (已登录会直接进; 未登录会跳 login.live.com)
    page.goto(_ORDERS_URL, wait_until="domcontentloaded", timeout=30_000)

    # 处理登录(如果被跳到登录页)
    if page.url.startswith(_LOGIN_URL_PREFIX):
        login_result = _do_login(page, login_email, password_plain)
        if login_result is not None:
            return login_result  # 失败时直接返回失败结构

        # 登录成功 → 再访问订单页(有时登录跳到首页)
        if not page.url.startswith("https://account.microsoft.com/billing/orders"):
            page.goto(_ORDERS_URL, wait_until="domcontentloaded", timeout=30_000)

    # 已登录,等订单卡片出来
    try:
        page.wait_for_selector("text=Order number", timeout=20_000)
    except PlaywrightTimeout:
        return FetchResult(
            success=False,
            orders=[],
            balance=None,
            failure_category="order_page_failed",
            failure_message="订单卡片未在 20 秒内渲染(可能页面结构变化或无任何订单)",
        )

    orders = _parse_orders(page, limit=count)
    # 余额: 截图未显示余额, billing 余额可能在 /billing 主页 或者跳过(暂不抓)
    return FetchResult(success=True, orders=orders, balance=None)


def _do_login(page: Page, email: str, password: str) -> Optional[FetchResult]:
    """登录流程。成功返回 None,失败返回 FetchResult(success=False)。"""
    try:
        # 邮箱
        page.wait_for_selector('input[name="loginfmt"]', timeout=15_000)
        page.fill('input[name="loginfmt"]', email)
        page.click('input[type="submit"]')

        # 密码
        page.wait_for_selector('input[name="passwd"]', timeout=15_000)
        page.fill('input[name="passwd"]', password)
        page.click('input[type="submit"]')

        # 检测密码错(URL 不变 + 出现错误提示)
        try:
            page.wait_for_load_state("networkidle", timeout=8_000)
        except PlaywrightTimeout:
            pass

        url = page.url
        body_text = page.content().lower()

        if "your account or password is incorrect" in body_text or "incorrect" in body_text and "password" in body_text:
            return FetchResult(
                success=False,
                orders=[],
                balance=None,
                failure_category="password_error",
                failure_message="Microsoft 提示账号或密码错误",
            )

        # 2FA / 验证码
        if "/proofs/" in url or "verify" in url or "two-step" in body_text:
            return FetchResult(
                success=False,
                orders=[],
                balance=None,
                failure_category="verification_required",
                failure_message="账号触发二步验证(请在 headed 模式手动完成一次,信任设备建立后再来)",
            )

        # "Stay signed in?" - 点 Yes 让 cookies 持久
        try:
            yes_btn = page.locator('input[id="idSIButton9"], input[value="Yes"]')
            if yes_btn.count() > 0:
                yes_btn.first.click(timeout=5_000)
        except Exception:
            pass

        return None  # 成功

    except PlaywrightTimeout as exc:
        return FetchResult(
            success=False,
            orders=[],
            balance=None,
            failure_category="login_page_changed",
            failure_message=f"登录页元素未找到(Microsoft 可能改了 DOM): {exc}",
        )


def _parse_orders(page: Page, limit: int) -> list[FetchedOrder]:
    """解析订单页面,返回最多 ``limit`` 条订单。

    根据 CEO 2026-05-12 截图,订单卡格式:
    - 顶部行: "May 11, 2026 | Order number 8035392088"
    - 商品名: 单独一行
    - 金额: "USD$0.99" / "GBP£0.99"

    页面用 React 渲染, 每个卡片是独立 div。我们通过 text=Order number 找到锚点,
    然后向上找父容器拿整张卡片的纯文本,再用正则提取。
    """
    # 找所有"Order number"文本节点的所在卡片容器
    cards = page.locator("text=Order number").locator(
        'xpath=ancestor::*[contains(@class, "card") or self::section or self::article][1]'
    )
    card_count = cards.count()

    out: list[FetchedOrder] = []
    seen_order_nos: set[str] = set()

    for i in range(min(card_count, limit * 3)):  # 多取一点冗余,防止解析失败丢
        if len(out) >= limit:
            break
        try:
            card = cards.nth(i)
            text = card.inner_text(timeout=5_000)
        except Exception:
            continue

        order = _parse_one_card(text)
        if order is None:
            continue
        if order.order_no in seen_order_nos:
            continue
        seen_order_nos.add(order.order_no)
        out.append(order)

    # fallback: 如果 xpath 没匹配到(DOM 结构变了),用整页文本切分
    if not out:
        out = _parse_orders_fallback(page, limit)

    return out


def _parse_one_card(text: str) -> Optional[FetchedOrder]:
    """从单个卡片纯文本里抓出订单字段。"""
    order_no_m = _ORDER_NO_RE.search(text)
    if not order_no_m:
        return None
    order_no = order_no_m.group(1)

    date_m = _DATE_RE.search(text)
    if not date_m:
        return None
    month = _MONTH_NAMES[date_m.group(1)]
    day = int(date_m.group(2))
    year = int(date_m.group(3))
    # Microsoft 页面只精确到天 → 用当天 12:00:00 (避免时区跨日)
    order_at = datetime(year, month, day, 12, 0, 0)

    price_m = _PRICE_RE.search(text)
    if not price_m:
        return None
    currency_symbol = price_m.group(1)
    amount = Decimal(price_m.group(2).replace(",", ""))
    if "USD" in currency_symbol or "$" in currency_symbol:
        currency = "USD"
    elif "GBP" in currency_symbol or "£" in currency_symbol:
        currency = "GBP"
    else:
        currency = "USD"  # 兜底

    return FetchedOrder(
        order_no=order_no,
        amount_local=amount,
        currency_local=currency,
        order_at=order_at,
        raw_data={"source": "playwright", "card_text_preview": text[:200]},
    )


def _parse_orders_fallback(page: Page, limit: int) -> list[FetchedOrder]:
    """整页文本兜底解析(如果 card 选择器失效)。

    思路: 找页面所有"Order number XXX"位置,以这些位置为分隔切片处理。
    """
    full_text = page.inner_text("body", timeout=5_000)
    splits = re.split(r"(?=Order\s+number\s+\d+)", full_text)
    out: list[FetchedOrder] = []
    seen: set[str] = set()
    for chunk in splits:
        if len(out) >= limit:
            break
        order = _parse_one_card(chunk)
        if order and order.order_no not in seen:
            seen.add(order.order_no)
            out.append(order)
    return out


# ---------------------------------------------------------------------------
# 首次设置辅助 (供 CEO 手动登录建立信任设备)
# ---------------------------------------------------------------------------


def first_run_login(login_email: str, password_plain: str, timeout_seconds: int = 300) -> str:
    """开发模式: 启动 headed Chromium 让 CEO 手动完成 2FA + 信任设备,
    完成后 cookies 自动落到 user_data_dir,后续 headless 可复用。

    用法 (在 Python REPL 或脚本):
        from src.services.xbox_playwright import first_run_login
        first_run_login("xbox@test.com", "real_password")
    """
    os.environ["XBOX_PLAYWRIGHT_HEADLESS"] = "false"
    with sync_playwright() as p:
        ctx = _launch_context(p)
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(_ORDERS_URL, wait_until="domcontentloaded", timeout=30_000)
            print(f"[first_run_login] 浏览器已打开, 请手动完成登录 + 2FA + 信任设备...")
            print(f"[first_run_login] 完成后页面 URL 应为: {_ORDERS_URL}")
            print(f"[first_run_login] 等待最多 {timeout_seconds} 秒...")
            # 等用户手动登录到订单页
            page.wait_for_url(f"{_ORDERS_URL}**", timeout=timeout_seconds * 1000)
            print(f"[first_run_login] ✓ 登录成功 + cookies 已写入 {_user_data_dir()}")
            return f"OK cookies in {_user_data_dir()}"
        finally:
            ctx.close()
