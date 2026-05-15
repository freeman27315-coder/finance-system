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
- XBOX_PLAYWRIGHT_COOKIE_DIR (默认 ./.playwright-cookies)
  每账号 cookies 存 cookies/account_{account_id}.json (CEO 2026-05-15)
- XBOX_PLAYWRIGHT_HEADLESS (默认 true; 首次手动登录时设 false 看着完成 2FA)
"""
from __future__ import annotations

import asyncio
import json
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


def _cookie_dir() -> Path:
    """CEO 2026-05-15: 每账号一个 cookies/{account_id}.json 文件。
    不再用 launch_persistent_context 共享 Chrome profile, 避免账号 A 的
    cookies 污染账号 B 的同步。
    """
    raw = os.environ.get("XBOX_PLAYWRIGHT_COOKIE_DIR")
    if raw:
        p = Path(raw).expanduser().resolve()
    else:
        p = (Path.cwd() / ".playwright-cookies").resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def _cookie_path(account_id: int) -> Path:
    return _cookie_dir() / f"account_{account_id}.json"


def _save_cookies(context: BrowserContext, account_id: int) -> None:
    """登录成功后调一次, 把 context 当前 cookies 序列化写盘。"""
    try:
        cookies = context.cookies()
        _cookie_path(account_id).write_text(
            json.dumps(cookies, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass  # 落盘失败不阻塞同步流程


def _load_cookies(context: BrowserContext, account_id: int) -> bool:
    """启动 context 后调一次, 把 cookies 注入。返回是否加载到内容。"""
    path = _cookie_path(account_id)
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not data:
            return False
        context.add_cookies(data)
        return True
    except Exception:
        return False


def _is_logged_in(page: Page) -> bool:
    """注入 cookies 后, 访问主页看是否还在登录域。
    True = cookies 有效, 可直接抓订单;
    False = 失效, 需要走完整登录。
    """
    try:
        page.goto(
            "https://account.microsoft.com/",
            wait_until="domcontentloaded",
            timeout=15_000,
        )
        page.wait_for_timeout(2_000)
    except Exception:
        return False
    return (
        "login.live.com" not in page.url
        and "login.microsoftonline.com" not in page.url
    )


def _apply_stealth(page: Page) -> None:
    """playwright-stealth 反检测脚本注入。headless 模式必备, 防 Microsoft
    用 navigator.webdriver / chrome.runtime 等 40+ 检测点识别我们是自动化。
    安装失败/版本不兼容 → 跳过, 不阻塞主流程。
    """
    try:
        from playwright_stealth import Stealth
        Stealth().apply_stealth_sync(page)
    except Exception:
        pass


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

    return _run_in_worker_thread(
        account.id, account.login_email, password_plain, count
    )


def _run_in_worker_thread(
    account_id: int, login_email: str, password_plain: str, count: int
) -> FetchResult:
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
                    browser, ctx = _launch_context(p)
                    try:
                        # 注入本账号 cookies (如有), 让 Microsoft 看到老身份免 2FA
                        _load_cookies(ctx, account_id)
                        page = ctx.new_page()
                        _apply_stealth(page)
                        result_holder["result"] = _do_fetch(
                            page,
                            ctx,
                            account_id,
                            login_email,
                            password_plain,
                            count,
                        )
                    finally:
                        try:
                            ctx.close()
                        except Exception:
                            pass
                        try:
                            browser.close()
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


def _launch_context(p: Playwright) -> tuple[Browser, BrowserContext]:
    """启动 browser + 全新 context (CEO 2026-05-15 改造)。

    旧版用 launch_persistent_context + user_data_dir, 所有账号共享一个
    Chrome profile, 后果是账号 B 同步抓出了账号 A 的数据。现在每账号一
    JSON cookie 文件, context 创建时 _load_cookies 各自注入, 互不干扰。
    """
    browser_pref = os.environ.get("XBOX_PLAYWRIGHT_BROWSER", "chrome").lower()
    want_headless = _is_headless()
    args = [
        "--disable-blink-features=AutomationControlled",
        "--disable-features=WebAuthenticationConditionalUI,Translate,MediaRouter,OptimizationHints",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-default-apps",
        "--disable-extensions",
        "--disable-component-update",
        "--disable-sync",
        "--window-size=1280,800",
    ]
    if want_headless:
        args.append("--headless=new")

    launch_kwargs = dict(headless=False, args=args)
    if browser_pref in {"chrome", "msedge"}:
        browser = p.chromium.launch(channel=browser_pref, **launch_kwargs)
    else:
        browser = p.chromium.launch(**launch_kwargs)

    context = browser.new_context(
        locale="zh-CN",
        timezone_id="Asia/Shanghai",
        viewport={"width": 1280, "height": 800},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
    )

    # 拦截不必要资源(图片/字体/媒体/广告)— 速度提升 2-5x
    def _block_unwanted(route, request):
        rt = request.resource_type
        url = request.url.lower()
        if rt in {"image", "media", "font"}:
            route.abort()
            return
        if any(d in url for d in (
            "google-analytics.com", "googletagmanager.com", "doubleclick.net",
            "bing.com/insightservice", "clarity.ms", "scorecardresearch.com",
            "ads.microsoft.com",
        )):
            route.abort()
            return
        route.continue_()

    context.route("**/*", _block_unwanted)
    return browser, context


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
    context: BrowserContext,
    account_id: int,
    login_email: str,
    password_plain: str,
    count: int,
) -> FetchResult:
    """登录(尽量复用 cookie)+ 拉订单 + 拉余额。

    CEO 2026-05-15 流程改造:
      1. cookies 已在外层 _load_cookies 注入(若 JSON 文件存在)
      2. _is_logged_in 通过访问主页验证 — 不在 login 域 = 复用成功
      3. 复用失败 → 走完整登录 _full_login(自动处理弹窗) → _save_cookies
      4. 抓订单 (含懒加载滚动 + Show more)
      5. 抓余额
    """
    # Step 1: 验证 cookies 是否仍有效
    logged_in = _is_logged_in(page)

    # Step 2: cookies 失效 → 完整登录
    if not logged_in:
        login_ok = _full_login(page, login_email, password_plain)
        if not login_ok:
            return FetchResult(
                success=False,
                orders=[],
                balance=None,
                failure_category="login_failed",
                failure_message=(
                    "完整登录失败(账号密码 / 安全验证 / 弹窗未处理)。"
                    f"final_url={page.url[:200]}"
                ),
            )
        # 登录成功 → 把最新 cookies 落盘, 下次直接复用
        _save_cookies(context, account_id)

    # Step 3: 进订单页
    _goto_with_retry(page, _ORDERS_URL, wait_until="commit", timeout=30_000)

    # "Is your security info still accurate?" 提示页 - 自动点 Looks good
    if "proofs" in page.url:
        try:
            for label in ["Looks good!", "Looks good", "看起来不错"]:
                btn = page.get_by_role("button", name=label, exact=False)
                if btn.count() > 0:
                    btn.first.click(timeout=3_000)
                    break
        except Exception:
            pass

    # 兜底再 goto 一次(若中途跳走)
    if "account.microsoft.com/billing/orders" not in page.url:
        _goto_with_retry(page, _ORDERS_URL, wait_until="commit", timeout=30_000)

    # 直接等订单卡片 — 不用 networkidle (Microsoft 后台 XHR 永不停)
    try:
        page.wait_for_selector("text=Order number", timeout=20_000)
    except PlaywrightTimeout:
        # 调试: 把页面 URL + 截图 + body text 写文件
        dbg_dir = _cookie_dir() / "debug"
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
    # password_plain 传进去, 因为 Microsoft 把 /billing/payments 视为
    # 高敏感页, 即使 cookies 有效也会再次要求输密码。
    balance = _try_fetch_balance(page, password_plain)
    return FetchResult(success=True, orders=orders, balance=balance)


def _try_fetch_balance(page: Page, password_plain: str) -> Optional[FetchedBalance]:
    """爬 Microsoft 账户余额。失败返回 None, 不阻塞主流程。

    Microsoft 把账户余额(Microsoft account balance / Microsoft 帐户余额)
    放在 https://account.microsoft.com/billing 概览页/付款页右上角徽章里。
    CEO 2026-05-14 截图: "Microsoft 帐户余额: 0.28 USD"
    — 币种 USD 在数字**后**, 不是前。
    """
    debug_dir = _cookie_dir() / "debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    debug_path = debug_dir / "balance_fetch.txt"
    body_text = ""
    final_url = ""

    try:
        # CEO 2026-05-14 调试 + 截图证据:
        #   /billing → 301 redirect 回 /billing/orders, 不显示余额
        #   /billing/payments → Microsoft reauth(高敏感页)
        #   ✅ 账户主页 / 直接显示 "Microsoft account balance (USD 0.28)"
        #     在"付款选项"折叠区, 不需要 reauth
        _goto_with_retry(
            page,
            "https://account.microsoft.com/",
            wait_until="commit",
            timeout=30_000,
        )

        # 兜底: 万一主页也被 reauth 拦住 (不该出现, 留作防御)
        if "login.live.com" in page.url or "login.microsoftonline.com" in page.url:
            try:
                page.wait_for_selector(
                    'input[name="passwd"]', state="visible", timeout=6_000
                )
                page.fill('input[name="passwd"]', password_plain)
                _click_submit(page)
                try:
                    page.wait_for_url("**account.microsoft.com**", timeout=15_000)
                except PlaywrightTimeout:
                    pass
            except PlaywrightTimeout:
                pass

        # 等"账户余额"字样出现(中英文任一)
        for sel in (
            "text=Microsoft account balance",
            "text=Microsoft 帐户余额",
            "text=Microsoft 账户余额",
            "text=Account balance",
        ):
            try:
                page.wait_for_selector(sel, timeout=8_000)
                break
            except PlaywrightTimeout:
                continue

        # 如果"付款选项"是折叠状态, 展开一下让余额可见
        try:
            for btn_label in ("付款选项", "Payment options", "Payment & billing"):
                btn = page.get_by_role("button", name=btn_label, exact=False)
                if btn.count() > 0:
                    try:
                        btn.first.click(timeout=2_000)
                        page.wait_for_timeout(800)
                    except Exception:
                        pass
                    break
        except Exception:
            pass

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


def _click_first(page: Page, selectors: list[str]) -> bool:
    """逐个尝试 selector, 找到第一个能点的就点。返回是否点到。"""
    for sel in selectors:
        try:
            loc = page.locator(sel)
            if loc.count() > 0:
                loc.first.click(timeout=2_000)
                return True
        except Exception:
            continue
    return False


def _select_password_option(page: Page, email: str) -> None:
    """Microsoft 在某些账号上推 passkey, 进"选择登录方式"页, 没有密码框。
    检测到时遍历"登录方式"选项, 找到能露出密码框的那个。
    CEO 2026-05-15 文档实现, 优先 idx=1(密码通常在第二位)。
    """
    pwd_sel = "input[type='password'], #i0118"
    opts_sel = "span[role='button'], [role='option']"
    if page.locator(pwd_sel).count() > 0:
        return
    try:
        total = page.locator(opts_sel).count()
    except Exception:
        return
    if total == 0:
        return
    priority = [1] + [i for i in range(total) if i != 1]
    for idx in priority:
        try:
            page.locator(opts_sel).nth(idx).click(timeout=2_000)
            page.wait_for_timeout(1_800)
            if page.locator(pwd_sel).count() > 0:
                return
            # 没出现密码框 → 回退重试
            try:
                page.go_back(wait_until="domcontentloaded", timeout=10_000)
                page.wait_for_timeout(1_000)
            except Exception:
                pass
            # 回退到邮箱页 → 重填提交
            if page.locator("input[type='email']").count() > 0:
                page.locator("input[type='email']").fill(email)
                try:
                    page.locator("input[type='submit']").first.click(timeout=3_000)
                except Exception:
                    pass
                page.wait_for_timeout(3_000)
        except Exception:
            continue


def _handle_login_prompts(page: Page) -> str:
    """Microsoft 登录后弹窗循环处理(最多 14 轮)。
    Privacy Notice / KMSI / 安全信息绑定 / 挂起页 / 通用推进。
    返回 'success' 或 'failed'。CEO 2026-05-15 文档实现。
    """
    for _ in range(14):
        url = page.url

        # 1. Privacy Notice (隐私声明)
        if "privacynotice.account.microsoft.com" in url:
            _click_first(page, [
                "button[type='submit']",
                "button[autofocus]",
                "#id__0",
                "input[type='submit']",
            ])
            page.wait_for_timeout(2_000)
            continue

        # 2. KMSI 保持登录 — 点 Yes 延长 cookie 寿命
        if "ppsecure" in url or "kmsi" in url.lower():
            try:
                body = page.inner_text("body", timeout=3_000).lower()
                if any(p in body for p in (
                    "stay signed in", "keep me signed in",
                    "保持登录", "保持登陆",
                )):
                    yes = page.locator("#idSIButton9, button[type='submit']")
                    if yes.count() > 0:
                        yes.first.click(timeout=3_000)
                        page.wait_for_timeout(2_000)
                        continue
            except Exception:
                pass

        # 3. 安全信息绑定弹窗 → 找 Skip / Cancel 跳过
        try:
            body_for_security = (
                page.inner_text("body", timeout=2_000)
                if page.locator("body").count() > 0
                else ""
            )
        except Exception:
            body_for_security = ""
        security_page = any(ph in body_for_security for ph in (
            "安全信息", "security info", "请补充", "验证方式",
            "add security", "verify your identity", "补充验证",
        ))
        if security_page:
            skipped = _click_first(page, [
                "button[data-testid='iCancel']",
                "#idBtn_Back",
                "button[data-testid='skip']",
                "#idA_SAASUI_Skip",
                "a[id*='Skip']",
                "a[id*='skip']",
            ])
            if skipped:
                page.wait_for_timeout(2_500)
                continue

        # 4. 挂起的安全操作 — go_back 无效, 强制重导
        try:
            body_for_pending = (
                page.inner_text("body", timeout=2_000)
                if page.locator("body").count() > 0
                else ""
            )
        except Exception:
            body_for_pending = ""
        if "挂起" in body_for_pending or "pending" in body_for_pending.lower():
            try:
                page.goto(
                    "https://login.live.com/",
                    wait_until="domcontentloaded",
                    timeout=20_000,
                )
                page.wait_for_timeout(1_000)
            except Exception:
                pass
            continue

        # 5. 已离开登录域 → 登录完成
        login_domains = ("login.live.com", "login.microsoftonline.com")
        interrupter_path = re.search(
            r"/(fido|secinfo|recovery|kmsi|add-info)", url
        )
        if not any(d in url for d in login_domains) and not interrupter_path:
            if any(d in url for d in ("microsoft.com", "xbox.com", "live.com")):
                return "success"

        # 6. 无明显特征 → 通用推进按钮
        _click_first(page, [
            "#idSIButton9",
            "input[type='submit']",
            "button[type='submit']",
            "button[autofocus]",
        ])
        page.wait_for_timeout(2_500)

    return "failed"


def _full_login(page: Page, email: str, password: str) -> bool:
    """完整登录流程。cookies 失效 / 首次时调。
    流程:邮箱 → 选密码方式 → 密码 → 处理所有弹窗。返回是否成功。
    """
    # 0. 起点: login.live.com 或 page.url 已经在 login 流程
    if "login.live.com" not in page.url and "login.microsoftonline.com" not in page.url:
        try:
            page.goto(
                "https://login.live.com/",
                wait_until="domcontentloaded",
                timeout=20_000,
            )
        except Exception:
            pass

    # 1. 邮箱(若邮箱框可见)
    try:
        page.wait_for_selector(
            'input[name="loginfmt"], input[type="email"]',
            state="visible",
            timeout=10_000,
        )
        page.locator(
            'input[name="loginfmt"], input[type="email"]'
        ).first.fill(email)
        _click_submit(page)
        page.wait_for_timeout(2_000)
    except PlaywrightTimeout:
        # 邮箱框不可见 - 可能账号已被记住, 直接进密码页或选方式页
        pass

    # 2. 选择登录方式(若 Microsoft 推 passkey 而非密码)
    _select_password_option(page, email)

    # 3. 密码
    try:
        page.wait_for_selector(
            'input[name="passwd"], input[type="password"]',
            state="visible",
            timeout=10_000,
        )
        page.locator(
            'input[name="passwd"], input[type="password"]'
        ).first.fill(password)
        _click_submit(page)
        page.wait_for_timeout(2_000)
    except PlaywrightTimeout:
        # 密码框没出现 — 可能已经登录上(silent SSO 流程)
        # 让 _handle_login_prompts 兜底判断 success
        pass

    # 4. 处理所有后续弹窗 直到离开登录域
    return _handle_login_prompts(page) == "success"


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


# CEO 2026-05-15: first_run_login 旧手动登录入口已删除。
# 新方案: _full_login + _handle_login_prompts + playwright-stealth 实现
# 全自动完整登录, cookies 按账号 ID 分文件存储, 不再需要手动 2FA 步骤。
# (若某账号触发 Microsoft 强制 2FA, 同步会失败 + 报 verification_required)
