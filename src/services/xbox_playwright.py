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
import time
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


# CEO 2026-05-14: 网络瞬时抖动错误(WiFi 切换 / VPN 重连 / 短暂断网) -
# Chromium 抛 net::ERR_NETWORK_CHANGED 等错误码。
# page.goto 时遇到这类**瞬态**错误,自动重试,不直接整次同步失败。
_TRANSIENT_NET_ERRORS = (
    "ERR_NETWORK_CHANGED",
    "ERR_NETWORK_IO_SUSPENDED",
    "ERR_INTERNET_DISCONNECTED",
    "ERR_CONNECTION_RESET",
    "ERR_CONNECTION_CLOSED",
    "ERR_TIMED_OUT",
    "ERR_NAME_NOT_RESOLVED",
)


def _is_transient_net_error(exc: BaseException) -> bool:
    msg = str(exc)
    return any(code in msg for code in _TRANSIENT_NET_ERRORS)


def _goto_with_retry(
    page: Page,
    url: str,
    *,
    retries: int = 2,
    sleep_seconds: float = 1.5,
    **kwargs,
):
    """``page.goto`` 包裹瞬态网络错误自动重试(总尝试次数 = retries + 1)。"""
    for attempt in range(retries + 1):
        try:
            return page.goto(url, **kwargs)
        except Exception as exc:
            if attempt >= retries or not _is_transient_net_error(exc):
                raise
            time.sleep(sleep_seconds)


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

    CEO 2026-05-14: page.goto 自动重试 ERR_NETWORK_CHANGED 等瞬态错误。
    """
    _goto_with_retry(page, _ORDERS_URL, wait_until="commit", timeout=30_000)

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
            _goto_with_retry(page, _ORDERS_URL, wait_until="commit", timeout=30_000)

    # 兜底再 goto 一次(如果中间跳到首页等)
    if "account.microsoft.com/billing/orders" not in page.url:
        _goto_with_retry(page, _ORDERS_URL, wait_until="commit", timeout=30_000)

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

    # CEO 2026-05-14: Microsoft 订单页懒加载, 默认只渲染前 10~20 单。
    # 滚动 + 点 Show more 让卡片数量达到目标, 否则会漏单
    # (CEO 反馈: 实际 28 单, 之前只抓出 9 单)。
    _scroll_load_orders(page, target_count=count)

    orders = _parse_orders(page, limit=count)

    # CEO 2026-05-14: 之前真实抓取代码完全没爬余额(balance 一直传 None),
    # 导致 trigger_sync 永远跳过更新 account.local_balance。
    # 这里跳到 billing 概览页爬一次余额, 失败不影响订单抓取。
    balance = _try_fetch_balance(page)
    return FetchResult(success=True, orders=orders, balance=balance)


def _try_fetch_balance(page: Page) -> Optional[FetchedBalance]:
    """爬 Microsoft 账户余额。失败返回 None, 不阻塞主流程。

    Microsoft 把账户余额(Microsoft account balance / Microsoft 帐户余额)
    放在 https://account.microsoft.com/billing 概览页/付款页右上角徽章里。
    CEO 2026-05-14 截图: "Microsoft 帐户余额: 0.28 USD"
    — 币种 USD 在数字**后**, 不是前。
    """
    debug_dir = _user_data_dir().parent / "debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    debug_path = debug_dir / "balance_fetch.txt"
    body_text = ""
    final_url = ""

    try:
        _goto_with_retry(
            page,
            "https://account.microsoft.com/billing",
            wait_until="commit",
            timeout=30_000,
        )
        # 等出现"余额"字样(中英文任一)
        for sel in ("text=余额", "text=Microsoft account balance", "text=Balance"):
            try:
                page.wait_for_selector(sel, timeout=8_000)
                break
            except PlaywrightTimeout:
                continue
        final_url = page.url
        body_text = page.inner_text("body", timeout=10_000)
    except Exception as exc:
        try:
            debug_path.write_text(
                f"EXCEPTION during balance fetch: {type(exc).__name__}: {exc}\n"
                f"final_url={final_url}\n",
                encoding="utf-8",
            )
        except Exception:
            pass
        return None

    # 两步匹配:
    # 1) 先用关键字定位到"余额"那一小段
    # 2) 在关键字之后 100 字符内, 匹配金额 + 币种(币种可在前或后)
    keyword_re = re.compile(
        r"(?:Microsoft account balance|Microsoft 帐户余额|Microsoft 账户余额"
        r"|Account balance|Account credit|Available credit"
        r"|账户余额|账号余额|帐户余额|余额)",
        re.IGNORECASE,
    )
    m = keyword_re.search(body_text)
    if not m:
        try:
            debug_path.write_text(
                f"NO KEYWORD MATCH\nfinal_url={final_url}\n"
                f"---body_text (first 3000 chars)---\n{body_text[:3000]}\n",
                encoding="utf-8",
            )
        except Exception:
            pass
        return None

    segment = body_text[m.end() : m.end() + 100]

    # 在段里找金额+币种 (币种 USD/GBP/EUR/TWD/JPY/CNY 在数字前后都行)
    amount_re = re.compile(
        r"(?:"
        r"(?P<cur_before>USD|GBP|EUR|TWD|JPY|CNY)\s*[\$£€¥]?\s*(?P<num_a>[\d,]+\.\d{1,2})"
        r"|"
        r"[\$£€¥]\s*(?P<num_b>[\d,]+\.\d{1,2})\s*(?P<cur_b>USD|GBP|EUR|TWD|JPY|CNY)?"
        r"|"
        r"(?P<num_c>[\d,]+\.\d{1,2})\s*(?P<cur_after>USD|GBP|EUR|TWD|JPY|CNY)"
        r")",
        re.IGNORECASE,
    )
    m2 = amount_re.search(segment)
    if not m2:
        try:
            debug_path.write_text(
                f"KEYWORD HIT BUT NO AMOUNT MATCH\nfinal_url={final_url}\n"
                f"keyword='{m.group(0)}' at pos {m.start()}-{m.end()}\n"
                f"segment(100chars)={segment!r}\n"
                f"---body_text (3000 chars around keyword)---\n"
                f"{body_text[max(0, m.start()-200) : m.end()+800]}\n",
                encoding="utf-8",
            )
        except Exception:
            pass
        return None

    num = (
        m2.group("num_a") or m2.group("num_b") or m2.group("num_c") or ""
    ).replace(",", "")
    cur = (
        m2.group("cur_before")
        or m2.group("cur_after")
        or m2.group("cur_b")
        or "USD"
    ).upper()
    if not num:
        return None
    try:
        result = FetchedBalance(currency=cur, balance=Decimal(num))
        try:
            debug_path.write_text(
                f"OK balance={result.balance} {result.currency}\n"
                f"final_url={final_url}\nkeyword='{m.group(0)}' segment={segment!r}\n",
                encoding="utf-8",
            )
        except Exception:
            pass
        return result
    except Exception:
        return None


def _scroll_load_orders(
    page: Page, target_count: int, max_iters: int = 20
) -> None:
    """滚动到底并点击 "Show more" 按钮, 直到加载够 target_count 条订单卡片
    或确认没更多可加载了。

    CEO 2026-05-14: Microsoft `/billing/orders` 页是懒加载, 首屏只渲染
    前 10~20 条订单卡, 必须滚动 / 点扩展按钮才能拉出剩下的。

    停止条件(任一满足即返回):
      - 已加载卡片数 >= target_count
      - 连续 3 次滚动后卡片数不再增长, 且没找到可点的"加载更多"按钮
      - 超过 max_iters 次迭代(防死循环)
    """
    last_count = 0
    stagnant = 0
    more_button_labels = (
        "Show more",
        "Load more",
        "See more",
        "More orders",
        "查看更多",
        "加载更多",
        "显示更多",
    )

    for _ in range(max_iters):
        current = page.locator("text=Order number").count()
        if current >= target_count:
            return

        # 滚动到页面底部触发懒加载
        try:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        except Exception:
            pass
        page.wait_for_timeout(1_500)

        # 看一下卡片数有没有增加
        new_count = page.locator("text=Order number").count()
        if new_count > current:
            last_count = new_count
            stagnant = 0
            continue

        # 滚动没新增 → 试点 Show more / Load more 按钮
        clicked = False
        for label in more_button_labels:
            try:
                btn = page.get_by_role("button", name=label, exact=False)
                if btn.count() > 0 and btn.first.is_visible():
                    btn.first.click(timeout=2_000)
                    page.wait_for_timeout(2_000)
                    clicked = True
                    break
            except Exception:
                continue

        if clicked:
            stagnant = 0
            continue

        # 既没新增也没按钮可点 → 认为没更多了, 累计停滞次数
        if new_count == last_count:
            stagnant += 1
            if stagnant >= 3:
                return
        else:
            last_count = new_count
            stagnant = 0


def _click_submit(page: Page, timeout_per_try: int = 8_000) -> None:
    """点击 Microsoft 登录页的"下一步 / 提交"按钮。

    CEO 2026-05-14: Microsoft 登录页按钮形态会变 (input[type=submit] /
    button[type=submit] / id=idSIButton9 等)。按优先级试,最后兜底按
    Enter 提交表单,避免单一 selector 没找到就整次同步失败。
    """
    selectors = (
        "#idSIButton9",            # Microsoft 老版标准 id (蓝色 Sign in)
        'button[type="submit"]',
        'input[type="submit"]',
        'button:has-text("Sign in")',
        'button:has-text("Next")',
    )
    for sel in selectors:
        try:
            page.click(sel, timeout=timeout_per_try)
            return
        except PlaywrightTimeout:
            continue
    # 所有 selector 都没找到 → 兜底按 Enter 触发表单 submit
    page.keyboard.press("Enter")


def _do_login(page: Page, email: str, password: str) -> Optional[FetchResult]:
    """登录流程。成功返回 None,失败返回 FetchResult(success=False)。

    CEO 2026-05-13: Microsoft 有时会"记住账号"(cookies 仍存了登录身份),
    登录页直接跳到密码输入界面,邮箱 input 变成 ``type=hidden``,
    导致原先 ``wait_for_selector(loginfmt, state=visible)`` 永远超时。
    修正:先用短超时探一下邮箱框是否可见 — 可见就走完整两步,
    不可见就只走密码步骤。

    CEO 2026-05-14: 提交按钮 selector 抽到 _click_submit 统一处理,
    多 selector 兜底 + Enter 键 fallback (Microsoft 改按钮 markup 时不挂)。

    CEO 2026-05-14 (二改): cookies 完全有效时 Microsoft 会走"静默 SSO"
    一连串 redirect (silent → sso → login.srf → /billing/orders),
    全程不需要填邮箱密码。进入 _do_login 不代表非要输密码; 先用 10s
    探一下是否已直达订单页, 是就直接 return None 走人。
    """
    try:
        # 静默 SSO 通过探测: 如果在 10s 内 URL 跳到了 /billing/orders
        # → 已经登录上, 不用填邮箱密码, 直接返回。
        try:
            page.wait_for_url(
                "**/billing/orders**", timeout=10_000
            )
            return None
        except PlaywrightTimeout:
            pass

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
            _click_submit(page)

        # 邮箱填完后, 再次探一下 SSO 是否在邮箱提交后直接跳过密码页
        try:
            page.wait_for_url(
                "**/billing/orders**", timeout=5_000
            )
            return None
        except PlaywrightTimeout:
            pass

        # 密码(必填)
        page.wait_for_selector(
            'input[name="passwd"]', state="visible", timeout=15_000
        )
        page.fill('input[name="passwd"]', password)
        _click_submit(page)

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
