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

import asyncio
import os
import re
import sys
import threading
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

    Windows + FastAPI 兼容性:
    FastAPI 在 thread pool 跑同步 endpoint 时, 线程默认 SelectorEventLoop 不支持
    subprocess → Playwright 启动 Chrome 时 NotImplementedError。
    所以在这里专开一个 worker thread, 设 ProactorEventLoop 再跑 Playwright。
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

    return _run_in_worker_thread(account.login_email, password_plain, count)


def _run_in_worker_thread(login_email: str, password_plain: str, count: int) -> FetchResult:
    """在独立 worker thread 里跑 Playwright,设 ProactorEventLoop(Windows)
    避免 FastAPI thread pool 的 SelectorEventLoop subprocess 报 NotImplementedError。
    """
    result_holder: dict = {"result": None}
    error_holder: dict = {"err": None}

    def _worker() -> None:
        try:
            # Windows 上必须用 ProactorEventLoop 才能 subprocess
            if sys.platform == "win32":
                asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                with sync_playwright() as p:
                    ctx = _launch_context(p)
                    try:
                        page = ctx.pages[0] if ctx.pages else ctx.new_page()
                        result_holder["result"] = _do_fetch(
                            page, login_email, password_plain, count
                        )
                    finally:
                        try:
                            ctx.close()
                        except Exception:
                            pass
            finally:
                try:
                    loop.close()
                except Exception:
                    pass
        except Exception as exc:
            error_holder["err"] = exc

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    t.join(timeout=180)  # 整体 3 分钟硬上限,防止 Playwright hang 死后端

    if t.is_alive():
        return FetchResult(
            success=False,
            orders=[],
            balance=None,
            failure_category="unknown",
            failure_message="Playwright 抓取超过 180 秒未返回(可能浏览器 hang 死)",
        )

    if error_holder["err"] is not None:
        return FetchResult(
            success=False,
            orders=[],
            balance=None,
            failure_category="unknown",
            failure_message=f"Playwright 抓取异常: {type(error_holder['err']).__name__}: {error_holder['err']}",
        )

    return result_holder["result"] or FetchResult(
        success=False,
        orders=[],
        balance=None,
        failure_category="unknown",
        failure_message="Playwright worker 返回空结果",
    )


# ---------------------------------------------------------------------------
# 流程内部
# ---------------------------------------------------------------------------


def _launch_context(p: Playwright) -> BrowserContext:
    """启动持久化浏览器上下文(cookies 存在 user_data_dir)。

    Windows 下 Playwright 自带的 Chromium 偶发缺 VC++ 运行时报
    "side-by-side configuration is incorrect"。
    优先用 Windows 系统的 Chrome(同 Chromium 引擎,用系统 runtime)。
    env XBOX_PLAYWRIGHT_BROWSER=chromium 强制走自带 Chromium。
    """
    # 默认用 Windows 系统的 Chrome (CEO 平时用 Chrome 登录 Microsoft, 视觉上一致)
    browser_pref = os.environ.get("XBOX_PLAYWRIGHT_BROWSER", "chrome").lower()
    want_headless = _is_headless()
    args = [
        "--disable-blink-features=AutomationControlled",  # 降低 bot 特征
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        # 加速启动: 关掉不必要功能
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-default-apps",
        "--disable-extensions",
        "--disable-component-update",
        "--disable-sync",
        "--disable-features=Translate,MediaRouter,OptimizationHints",
    ]
    if want_headless:
        # Chrome 109+ 新版 headless, 反爬识别率比传统 headless 低
        args.append("--headless=new")
    common_kwargs = dict(
        user_data_dir=str(_user_data_dir()),
        headless=False,  # 我们用 args=--headless=new 控制 (上面)
        args=args,
        viewport={"width": 1280, "height": 800},
        locale="en-US",
    )
    if browser_pref in {"chrome", "msedge"}:
        ctx = p.chromium.launch_persistent_context(channel=browser_pref, **common_kwargs)
    else:
        ctx = p.chromium.launch_persistent_context(**common_kwargs)

    # 拦截不必要资源(图片/字体/媒体/广告/Google Analytics)— 速度提升 2-5x
    def _block_unwanted(route, request):
        rt = request.resource_type
        url = request.url.lower()
        if rt in {"image", "media", "font"}:
            # 不拦 stylesheet (React 组件渲染时机依赖 CSS 加载)
            route.abort()
            return
        # 第三方追踪 / 分析
        if any(d in url for d in (
            "google-analytics.com", "googletagmanager.com", "doubleclick.net",
            "bing.com/insightservice", "clarity.ms", "scorecardresearch.com",
            "ads.microsoft.com",
        )):
            route.abort()
            return
        route.continue_()

    ctx.route("**/*", _block_unwanted)
    return ctx


def _do_fetch(
    page: Page,
    login_email: str,
    password_plain: str,
    count: int,
) -> FetchResult:
    """登录 + 拉订单。性能优化(CEO 2026-05-12):
    - 不用 networkidle (Microsoft 页面 XHR 永不停, 等满超时)
    - 直接等订单卡片 selector 出现
    - 资源拦截在 _launch_context 里 (图片/字体/广告)
    """
    page.goto(_ORDERS_URL, wait_until="commit", timeout=30_000)

    # "Is your security info still accurate?" 提示页 - 自动点 Looks good
    # 用短超时检测(没出现就跳过, 不阻塞主流程)
    if "proofs" in page.url:
        try:
            for label in ["Looks good!", "Looks good", "看起来不错"]:
                btn = page.get_by_role("button", name=label, exact=False)
                if btn.count() > 0:
                    btn.first.click(timeout=3_000)
                    break
        except Exception:
            pass

    # 处理登录(cookies 失效情况)
    if page.url.startswith(_LOGIN_URL_PREFIX):
        login_result = _do_login(page, login_email, password_plain)
        if login_result is not None:
            return login_result
        if "account.microsoft.com/billing/orders" not in page.url:
            page.goto(_ORDERS_URL, wait_until="commit", timeout=30_000)

    # 兜底再 goto 一次(如果中间跳到首页等)
    if "account.microsoft.com/billing/orders" not in page.url:
        page.goto(_ORDERS_URL, wait_until="commit", timeout=30_000)

    # 直接等订单卡片 — 不用 networkidle (Microsoft 后台 XHR 永不停)
    try:
        page.wait_for_selector("text=Order number", timeout=20_000)
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
    """登录流程。成功返回 None,失败返回 FetchResult(success=False)。

    CEO 2026-05-13: Microsoft 有时会"记住账号"(cookies 仍存了登录身份),
    登录页直接跳到密码输入界面,邮箱 input 变成 ``type=hidden``,
    导致原先 ``wait_for_selector(loginfmt, state=visible)`` 永远超时。
    修正:先用短超时探一下邮箱框是否可见 — 可见就走完整两步,
    不可见就只走密码步骤。
    """
    try:
        # 邮箱(可选 — 账号被记住时 Microsoft 会跳过)
        loginfmt_visible = False
        try:
            page.wait_for_selector(
                'input[name="loginfmt"]', state="visible", timeout=3_000
            )
            loginfmt_visible = True
        except PlaywrightTimeout:
            loginfmt_visible = False

        if loginfmt_visible:
            page.fill('input[name="loginfmt"]', email)
            page.click('input[type="submit"]')

        # 密码(必填)
        page.wait_for_selector(
            'input[name="passwd"]', state="visible", timeout=15_000
        )
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
    """从单个卡片纯文本里抓出订单字段。

    CEO 2026-05-12 截图卡片结构:
        May 11, 2026 | Order number 8035392088
        80 Robux                ← 商品名(独占一行)
        USD$0.99                ← 价格
        Completed
        Total USD$0.99
        Paid with Microsoft account
        Show details
    """
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

    # 商品名: 找 "Order number XXX" 那一行后面、价格行之前的非空行
    product_name = _extract_product_name(text, price_m.start())

    return FetchedOrder(
        order_no=order_no,
        amount_local=amount,
        currency_local=currency,
        order_at=order_at,
        product_name=product_name,
        raw_data={"source": "playwright", "card_text_preview": text[:200]},
    )


# 不应作为商品名的关键字(排除掉)
_NON_PRODUCT_NAME_TOKENS = {
    "Completed", "Pending", "Refunded", "Canceled", "Cancelled",
    "Show details", "Hide details", "Paid with", "Total",
}


def _extract_product_name(card_text: str, price_index: int) -> Optional[str]:
    """从卡片文本里提取商品名。

    策略: "Order number XXX" 行之后,价格 (USD$/GBP£) 之前的第一个非空行。
    通常就是商品名(如 "80 Robux" / "500 Robux")。
    """
    # 取"Order number"行 → 价格之间的片段
    order_idx = card_text.find("Order number")
    if order_idx < 0:
        return None
    # "Order number XXX\n" 后面到 price_index 之间的文本
    after_order_line_end = card_text.find("\n", order_idx)
    if after_order_line_end < 0:
        return None
    segment = card_text[after_order_line_end + 1 : price_index]
    for raw_line in segment.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        # 排除状态/操作类文字
        if any(token in line for token in _NON_PRODUCT_NAME_TOKENS):
            continue
        # 取第一个有效行作为商品名
        return line
    return None


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
