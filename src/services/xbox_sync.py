"""XBOX 订单同步引擎（FR-04 / IF-03）。

阶段 1（本 PR）：基础设施 + Mock 数据,不连真实 Microsoft
- 抓取实现是 stub,返回 3-5 个假订单
- 整套链路跑通（按钮 → 同步批次 → 写订单 → 失败标账号异常）
- CEO 看到"点同步 → 订单出现"的效果

阶段 2（CEO 提供真账号 + 页面截图后）：
- 把 _fetch_orders_microsoft_stub 替换成真实 Playwright 浏览器自动化
- 处理登录页 / 订单页 DOM 解析

业务规则（CEO 2026-05-08 + 2026-05-11 确认）：
- Q1A: 首次手动登录建立信任设备（阶段 2 前提）
- Q2A: 仅手动触发同步（无定时任务）
- Q3A: 失败标账号状态为 "error"（不发 Discord）
- FR-04.1: 同步条数 10/20/30/50

失败分类:
- "password_error": 密码错（账号被锁/改密码后）
- "verification_required": 需要安全验证（首次登录设备未授信）
- "login_page_changed": 登录页 DOM 变化（脚本要更新）
- "order_page_failed": 订单页访问失败
- "network_error": 网络错误
- "unknown": 未知
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.operator import Operator, XboxAccountClaim
from src.models.xbox import (
    XboxAccount,
    XboxAccountAuditLog,
    XboxAccountStatus,
    XboxBalanceSnapshot,
    XboxOrder,
    XboxOrderStatus,
    XboxSyncBatch,
)
from src.utils.time import china_now


# CEO 2026-05-15: 200 = "抓 Microsoft 过去 3 个月全部" 的语义值
# (实际 _scroll_load_orders 抓到没更多就停, 200 只是上限保险)。
# 客服 UI 上的 10/20/30/50 已改为"每页显示条数", 不再传给后端。
VALID_SYNC_COUNTS = (10, 20, 30, 50, 200)


# CEO 2026-05-12 Q1-A: 同步爬到 balance.currency 后自动识别国家
_CURRENCY_TO_COUNTRY = {
    "USD": ("US", "USD"),
    "GBP": ("UK", "GBP"),
}


def _identify_country_from_currency(currency: str) -> tuple[Optional[str], Optional[str]]:
    """USD→(US,USD), GBP→(UK,GBP), 其他→(None,None)"""
    return _CURRENCY_TO_COUNTRY.get(currency, (None, None))


def _apply_country_auto_detection(
    session: Session, account: XboxAccount, balance_currency: str
) -> None:
    """根据爬到的 balance.currency 自动设置账号的 country/currency,并写审计。

    - 第一次识别 (country_identified=False) → 设置 + audit + 标已识别
    - 重复识别 (已有值且一致) → 不动
    - 不一致 (CEO 改了账号 country 但同步抓到不同 currency) → 用同步值覆盖 + audit
    """
    identified_country, identified_currency = _identify_country_from_currency(balance_currency)
    if identified_country is None:
        # 未知币种,不做处理(stub 阶段不会发生)
        return

    old_country = account.country.value if hasattr(account.country, "value") else account.country
    old_currency = account.currency.value if hasattr(account.currency, "value") else account.currency
    if (
        account.country_identified
        and old_country == identified_country
        and old_currency == identified_currency
    ):
        return  # 已识别且一致,no-op

    account.country = identified_country
    account.currency = identified_currency
    account.country_identified = True
    session.add(
        XboxAccountAuditLog(
            account_id=account.id,
            action="updated",
            detail=(
                f"同步自动识别国家: {old_country}/{old_currency} → "
                f"{identified_country}/{identified_currency}"
            ),
            operator="sync",
        )
    )


# ---------------------------------------------------------------------------
# 仅拉余额 (CEO 2026-05-12 Q2: 刷新余额按钮使用,不污染订单数据)
# ---------------------------------------------------------------------------


def fetch_balance_only_stub(account: XboxAccount) -> Optional[FetchedBalance]:
    """阶段 1 stub: 模拟拉余额(不拉订单)。阶段 2 替换为真实 Playwright。

    返回 None 表示拉失败(未设登录邮箱/密码),否则返回 mock 余额 + 币种。
    Mock 规则:
    - 账号已识别国家 → 用现有 currency 模拟
    - 未识别 → 用 id%2 区分(演示自动识别效果)
    """
    if not account.login_email or not account.password_enc:
        return None

    if account.country_identified and account.currency:
        currency = account.currency.value if hasattr(account.currency, "value") else account.currency
    else:
        currency = "USD" if account.id % 2 == 0 else "GBP"

    # mock 余额: 每个账号有不同基数,以体现刷新差异
    balance = Decimal("123.45") + Decimal(account.id) * Decimal("10.00")
    return FetchedBalance(currency=currency, balance=balance)


def refresh_account_balance(session: Session, account: XboxAccount) -> dict:
    """刷新单个账号的微软余额 + 自动识别国家 + 写余额快照。

    不拉订单。返回 {success, balance, currency, country, message?}。
    """
    if account.status == XboxAccountStatus.DISABLED.value:
        return {
            "success": False,
            "message": "账号已停用",
            "balance": str(account.local_balance),
            "currency": account.currency.value if hasattr(account.currency, "value") else account.currency,
            "country": account.country.value if hasattr(account.country, "value") else account.country,
        }

    fetched = fetch_balance_only_stub(account)
    if fetched is None:
        return {
            "success": False,
            "message": "账号未设置登录邮箱或密码",
            "balance": str(account.local_balance),
            "currency": account.currency.value if hasattr(account.currency, "value") else account.currency,
            "country": account.country.value if hasattr(account.country, "value") else account.country,
        }

    # 写快照
    snapshot = XboxBalanceSnapshot(
        account_id=account.id,
        currency=fetched.currency,
        balance=Decimal(fetched.balance),
        captured_at=china_now(),
    )
    session.add(snapshot)

    # 自动识别国家
    _apply_country_auto_detection(session, account, fetched.currency)

    # 更新余额 + last_synced_at
    account.local_balance = Decimal(fetched.balance)
    account.last_synced_at = china_now()
    session.flush()

    return {
        "success": True,
        "balance": str(fetched.balance),
        "currency": fetched.currency,
        "country": account.country.value if hasattr(account.country, "value") else account.country,
    }


@dataclass
class FetchedOrder:
    """从 Microsoft 抓到的单个订单原始字段。"""

    order_no: str
    amount_local: Decimal
    currency_local: str  # USD / GBP
    order_at: datetime
    product_name: Optional[str] = None  # CEO 2026-05-12: Microsoft 商品名 (如 "80 Robux")
    raw_data: Optional[dict] = None


@dataclass
class FetchedBalance:
    """账号当前本币余额。"""

    currency: str
    balance: Decimal


@dataclass
class FetchResult:
    """抓取结果。success=True 时 orders/balance 有效；False 时 failure_* 有效。"""

    success: bool
    orders: list[FetchedOrder]
    balance: Optional[FetchedBalance]
    failure_category: Optional[str] = None
    failure_message: Optional[str] = None


# ---------------------------------------------------------------------------
# 阶段 1: Stub 抓取（CEO 给真账号后阶段 2 替换）
# ---------------------------------------------------------------------------


def _fetch_orders_microsoft_stub(
    account: XboxAccount,
    count: int,
) -> FetchResult:
    """阶段 1 mock：返回 3-5 个假订单 + 假余额。让 CEO 看到整套流程效果。

    阶段 2 替换为真实 Playwright 抓取。
    """
    if not account.login_email or not account.password_enc:
        return FetchResult(
            success=False,
            orders=[],
            balance=None,
            failure_category="password_error",
            failure_message="账号未设置登录邮箱或密码",
        )

    # 模拟成功抓取
    now = china_now()
    currency = "USD" if account.country == "US" or (
        account.country.value if hasattr(account.country, "value") else account.country
    ) == "US" else "GBP"

    # 用账号 id + 时间戳生成不重复订单号
    timestamp = now.strftime("%Y%m%d%H%M%S")
    mock_orders = [
        FetchedOrder(
            order_no=f"MS-{account.id}-{timestamp}-{i}",
            amount_local=Decimal(["19.99", "59.99", "29.99", "9.99", "99.99"][i % 5]),
            currency_local=currency,
            order_at=now - timedelta(hours=i + 1),
            raw_data={"mock": True, "source": "stub"},
        )
        for i in range(min(count, 3))  # mock 只返回 3 个
    ]

    balance_value = Decimal("123.45")
    return FetchResult(
        success=True,
        orders=mock_orders,
        balance=FetchedBalance(currency=currency, balance=balance_value),
    )


# ---------------------------------------------------------------------------
# 主入口: 触发一次同步
# ---------------------------------------------------------------------------


def trigger_sync(
    session: Session,
    account: XboxAccount,
    count: int = 20,
) -> dict:
    """触发一次 Microsoft 订单同步。

    返回 ``{batchId, success, ordersAdded, ordersSkipped, balance, failure}``。

    流程：
    1. 校验 count ∈ {10,20,30,50}
    2. 建同步批次记录(started_at, status=running)
    3. 调 _fetch_orders_microsoft_stub (阶段 1) / 真实抓取 (阶段 2)
    4. 成功:
       - 按 order_no 去重写入 XboxOrder
       - 写余额快照
       - account.last_synced_at = now
       - batch.success=True, fetched_count=N
    5. 失败:
       - account.status = "error" + status_message
       - 写审计日志
       - batch.success=False, failure_category/message
    6. session.flush(),由调用方 commit
    """
    if count not in VALID_SYNC_COUNTS:
        raise ValueError(f"同步条数必须为 {VALID_SYNC_COUNTS} 之一,实际 {count}")

    now = china_now()
    batch = XboxSyncBatch(
        account_id=account.id,
        started_at=now,
        requested_count=count,
        fetched_count=0,
        success=False,
    )
    session.add(batch)
    session.flush()

    # 调抓取
    # CEO 2026-05-12 Q1-A/Q4: 默认 stub(单元测试用), .env 设 XBOX_SYNC_MODE=real
    # 即启 Playwright + Chromium 真实抓取。生产环境必须设 real。
    sync_mode = os.environ.get("XBOX_SYNC_MODE", "stub").lower()
    if sync_mode == "real":
        from src.services.xbox_playwright import fetch_microsoft_orders_real
        result = fetch_microsoft_orders_real(account, count)
    else:
        result = _fetch_orders_microsoft_stub(account, count)

    if not result.success:
        # 失败处理
        batch.finished_at = china_now()
        batch.success = False
        batch.failure_category = result.failure_category or "unknown"
        batch.failure_message = result.failure_message or "未知错误"

        # 标账号异常(CEO Q3A)
        old_status = account.status
        new_status_message = f"Microsoft 同步失败: {batch.failure_category}"
        if old_status != XboxAccountStatus.ERROR.value:
            account.status = XboxAccountStatus.ERROR.value
        account.status_message = new_status_message

        # 写审计
        session.add(
            XboxAccountAuditLog(
                account_id=account.id,
                action="status_changed",
                detail=f"自动同步失败 → 状态置 error: {batch.failure_category} - {result.failure_message}",
                operator="sync",
            )
        )

        session.flush()
        return {
            "batchId": batch.id,
            "success": False,
            "ordersAdded": 0,
            "ordersSkipped": 0,
            "balance": None,
            "failure": {
                "category": batch.failure_category,
                "message": batch.failure_message,
            },
        }

    # 成功 → 写订单(去重)
    # CEO 2026-05-13: 同步时如果该账号正被某客服领着,
    # **新订单**自动写经办人 = 该客服 display_name。
    # 仅作用于"新插入"的订单(已存在订单的 operator_name 不动,保持现状)。
    # 历史订单不回填(CEO 2026-05-13 Q1=A)。
    claim_operator_name: Optional[str] = session.scalar(
        select(Operator.display_name)
        .join(XboxAccountClaim, XboxAccountClaim.operator_id == Operator.id)
        .where(
            XboxAccountClaim.account_id == account.id,
            XboxAccountClaim.is_active.is_(True),
        )
    )

    orders_added = 0
    orders_skipped = 0
    for fetched in result.orders:
        existing = session.scalar(
            select(XboxOrder).where(XboxOrder.order_no == fetched.order_no)
        )
        if existing is not None:
            # CEO 2026-05-12: 旧订单可能缺商品名(早期抓取没解析), 补上来
            if fetched.product_name and not existing.product_name:
                existing.product_name = fetched.product_name
                existing.last_updated_at = china_now()
            orders_skipped += 1
            continue
        used_rate = account.exchange_rate
        if used_rate is None:
            rmb_cost = Decimal("0")
            used_rate_value = None
        else:
            rmb_cost = (Decimal(fetched.amount_local) * Decimal(used_rate)).quantize(
                Decimal("0.000001")
            )
            used_rate_value = Decimal(used_rate)
        order = XboxOrder(
            account_id=account.id,
            order_no=fetched.order_no,
            amount_local=Decimal(fetched.amount_local),
            currency_local=fetched.currency_local,
            exchange_rate=used_rate_value,
            rmb_cost=rmb_cost,
            order_at=fetched.order_at,
            # CEO 2026-05-12: 销售日期 = 微软订单时间(中国时区精确到秒),自动填
            sale_date=fetched.order_at,
            # CEO 2026-05-12: 商品名(如 "80 Robux"),从 Microsoft 卡片解析
            product_name=fetched.product_name,
            # CEO 2026-05-13: 经办人 = 当前领取该账号的客服(没人领→留空)
            operator_name=claim_operator_name,
            raw_data=fetched.raw_data,
            status=XboxOrderStatus.PENDING_COMPLETE.value,
        )
        session.add(order)
        orders_added += 1

    # 余额快照 + 同步更新账号当前余额(CEO 2026-05-12: 每次同步都更新 account.local_balance)
    balance_info = None
    if result.balance is not None:
        snapshot = XboxBalanceSnapshot(
            account_id=account.id,
            currency=result.balance.currency,
            balance=Decimal(result.balance.balance),
            captured_at=china_now(),
        )
        session.add(snapshot)
        # 更新账号当前余额,前端客服 exe 直接显示这个字段
        account.local_balance = Decimal(result.balance.balance)
        # CEO 2026-05-12: 根据爬回来的 currency 自动识别国家(USD→US, GBP→UK)
        _apply_country_auto_detection(session, account, result.balance.currency)
        balance_info = {
            "currency": result.balance.currency,
            "balance": str(result.balance.balance),
        }

    # 更新 batch + account
    batch.finished_at = china_now()
    batch.success = True
    batch.fetched_count = len(result.orders)
    account.last_synced_at = china_now()
    # 同步成功后如果账号之前是 error 状态,自动恢复 active
    if account.status == XboxAccountStatus.ERROR.value:
        account.status = XboxAccountStatus.ACTIVE.value
        account.status_message = None
        session.add(
            XboxAccountAuditLog(
                account_id=account.id,
                action="status_changed",
                detail="同步成功,状态自动恢复 error → active",
                operator="sync",
            )
        )

    session.flush()
    return {
        "batchId": batch.id,
        "success": True,
        "ordersAdded": orders_added,
        "ordersSkipped": orders_skipped,
        "balance": balance_info,
        "failure": None,
    }


def list_sync_batches(
    session: Session,
    account_id: Optional[int] = None,
    limit: int = 50,
) -> list[XboxSyncBatch]:
    stmt = select(XboxSyncBatch).order_by(XboxSyncBatch.id.desc()).limit(limit)
    if account_id is not None:
        stmt = stmt.where(XboxSyncBatch.account_id == account_id)
    return list(session.scalars(stmt))


def list_balance_snapshots(
    session: Session,
    account_id: int,
    limit: int = 20,
) -> list[XboxBalanceSnapshot]:
    return list(
        session.scalars(
            select(XboxBalanceSnapshot)
            .where(XboxBalanceSnapshot.account_id == account_id)
            .order_by(XboxBalanceSnapshot.id.desc())
            .limit(limit)
        )
    )
