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
    """返回 Playwright user_data 目录的**绝对路径**(必须绝对; Edge 启动后 CWD 不同
    导致相对路径解析失败,会报"无法创建数据目录")。"""
    raw = os.environ.get("XBOX_PLAYWRIGHT_USER_DATA_DIR")
    if raw:
        p = Path(raw).expanduser().resolve()
    else:
        p = (Path.cwd() / ".playwright-user-data" / "xbox").resolve()
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
    """启动持久化浏览器上下文(cookies 存在 user_data_dir)。

    Windows 下 Playwright 自带的 Chromium 偶发缺 VC++ 运行时报
    "side-by-side configuration is incorrect"。
    优先用 Windows 自带的 Microsoft Edge(同 Chromium 引擎,用系统 runtime)。
    env XBOX_PLAYWRIGHT_BROWSER=chromium 强制走自带 Chromium。
    """
    # 默认用 Windows 系统的 Chrome (CEO 平时用 Chrome 登录 Microsoft, 视觉上一致)
    # 注意: Playwright 控制的 Chrome 是**独立实例**, user_data_dir 独立,
    # 跟 CEO 平时用的 Chrome 浏览器隔离。第一次必须在 Playwright Chrome 里登录一次。
    browser_pref = os.environ.get("XBOX_PLAYWRIGHT_BROWSER", "chrome").lower()
    want_headless = _is_headless()
    args = [
        "--disable-blink-features=AutomationControlled",  # 降低 bot 特征
        # 真实 UA(Microsoft 对默认 Playwright UA 反爬严)
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    ]
    if want_headless:
        # Chrome 新版 headless 模式: 比传统 headless 更难被反爬识别
        args.append("--headless=new")
    common_kwargs = dict(
        user_data_dir=str(_user_data_dir()),
        # Playwright 的 headless=True 走旧 protocol, 反爬识别率 100%;
        # 我们用 args=--headless=new 控制 Chrome 实际 headless, Playwright 这边设 False。
        headless=False,
        args=args,
        viewport={"width": 1280, "height": 800},
        locale="en-US",
    )
    if browser_pref in {"chrome", "msedge"}:
        # 用 Windows 系统的 Chrome / Edge (channel='chrome' or 'msedge')
        return p.chromium.launch_persistent_context(channel=browser_pref, **common_kwargs)
    # chromium = Playwright 自带 (Windows 上可能缺 VC++ runtime)
    return p.chromium.launch_persistent_context(**common_kwargs)


def _do_fetch(
    page: Page,
    login_email: str,
    password_plain: str,
    count: int,
) -> FetchResult:
    """登录 + 拉订单。"""
    # 访问订单页 (已登录会直接进; 未登录会跳 login.live.com)
    # 用宽容的 "commit" 等待(只等服务器响应,不等完成),避免 Microsoft 大量后台
    # XHR 导致 domcontentloaded 超时。
    page.goto(_ORDERS_URL, wait_until="commit", timeout=60_000)

    # Microsoft 多重重定向 - 等所有跳转结束再判断
    try:
        page.wait_for_load_state("networkidle", timeout=45_000)
    except PlaywrightTimeout:
        pass

    # 处理"Is your security info still accurate?" 提示页 - 自动点 Looks good
    if "account.live.com/proofs/remind" in page.url or "proofs" in page.url:
        try:
            # 优先点 "Looks good" / 中文 "看起来不错" 按钮
            for label in ["Looks good!", "Looks good", "看起来不错", "看起来没问题"]:
                btn = page.get_by_role("button", name=label, exact=False)
                if btn.count() > 0:
                    btn.first.click(timeout=5_000)
                    break
        except Exception:
            pass
        try:
            page.wait_for_load_state("networkidle", timeout=20_000)
        except PlaywrightTimeout:
            pass

    # 处理登录(如果被跳到登录页且 cookies 失效)
    if page.url.startswith(_LOGIN_URL_PREFIX):
        login_result = _do_login(page, login_email, password_plain)
        if login_result is not None:
            return login_result  # 失败时直接返回失败结构

        # 登录成功 → 再访问订单页(有时登录跳到首页)
        if "account.microsoft.com/billing/orders" not in page.url:
            page.goto(_ORDERS_URL, wait_until="domcontentloaded", timeout=30_000)
            try:
                page.wait_for_load_state("networkidle", timeout=20_000)
            except PlaywrightTimeout:
                pass

    # 终极兜底: 如果到现在还没到订单页, 再 goto 一次
    if "account.microsoft.com/billing/orders" not in page.url:
        page.goto(_ORDERS_URL, wait_until="domcontentloaded", timeout=30_000)
        try:
            page.wait_for_load_state("networkidle", timeout=20_000)
        except PlaywrightTimeout:
            pass

    # 已登录,等订单卡片出来 (放宽超时 + 调试输出)
    try:
        # 等更宽容的条件:任何包含数字的内容,或者 "Order number" / "Past 3 months"
        page.wait_for_load_state("networkidle", timeout=30_000)
    except PlaywrightTimeout:
        pass

    try:
        page.wait_for_selector("text=Order number", timeout=30_000)
    except PlaywrightTimeout:
        # 调试: 把页面 URL + 截图 + body text 写文件
        dbg_dir = _user_data_dir().parent / "debug"
        dbg_dir.mkdir(parents=True, exist_ok=True)
        try:
            page.screenshot(path=str(dbg_dir / "no_orders.png"), full_page=True)
        except Exception:
            pass
        body_text = ""
        try:
            body_text = page.inner_text("body", timeout=5_000)
        except Exception:
            pass
        (dbg_dir / "no_orders.txt").write_text(
            f"URL: {page.url}\n\n--- BODY ---\n{body_text[:5000]}",
            encoding="utf-8",
        )
        return FetchResult(
            success=False,
            orders=[],
            balance=None,
            failure_category="order_page_failed",
            failure_message=(
                "订单卡片未渲染(URL={}). 调试快照: {}".format(page.url, dbg_dir)
            ),
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


def first_run_login(login_email: str, password_plain: str, timeout_seconds: int = 600) -> str:
    """开发模式: 启动 headed Chromium/Edge 让 CEO 手动完成 2FA + 信任设备,
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
            page.goto(_ORDERS_URL, wait_until="domcontentloaded", timeout=60_000)
            print("[first_run_login] 浏览器已打开. 请在浏览器中完成:")
            print("[first_run_login]   1) 填邮箱密码登录")
            print("[first_run_login]   2) 完成 2FA(邮箱/短信验证码)")
            print("[first_run_login]   3) 看到 'Stay signed in?' 点 Yes")
            print("[first_run_login]   4) 看到订单页(account.microsoft.com/billing/orders)")
            print(f"[first_run_login] 完成后,在浏览器里看到订单卡片 -> 关闭浏览器窗口即可")
            print(f"[first_run_login] 等待最多 {timeout_seconds} 秒...")
            # 等用户手动登录到订单页
            page.wait_for_url(
                lambda url: "account.microsoft.com/billing/orders" in url,
                timeout=timeout_seconds * 1000,
            )
            print(f"[first_run_login] OK -- LOGIN SUCCESS")
            print(f"[first_run_login] cookies written to {_user_data_dir()}")
            print("[first_run_login] 你现在可以关闭浏览器, 后续 trigger_sync 会自动复用 cookies")
            # 多等几秒让 cookies flush
            page.wait_for_timeout(3000)
            return f"OK cookies in {_user_data_dir()}"
        finally:
            try:
                ctx.close()
            except Exception:
                pass
