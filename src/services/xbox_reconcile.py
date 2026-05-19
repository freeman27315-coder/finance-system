"""XBOX 销售对账服务 (CEO 2026-05-20 #134 路径 2 重写)。

新口径(零中间层):
- XboxSaleRecord.wallet_pool_id 直接指向真实钱包(TAIWAN / TAOBAO group / ASSET_* 等)
- 应收 = SUM(sale_price) 按 wallet_pool_id + sale_date 汇总
- 实收 = 真实钱包当天 IN 净流水(group 钱包递归汇总子钱包)
- 差异 = 实收 - 应收

废弃:
- 不再区分理论/实际钱包
- 不再有 XboxReconcileMapping 映射表
- 不再有 ensure_xbox_default_* 启动建表逻辑

历史订单:
- 老订单的 wallet_pool_id 指向已 deleted_at 的 XBOX_SALES_LEDGER 钱包
- 报告里仍展示这些钱包(deleted=true 标记),排在末尾,供 CEO 看历史
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import and_, func as sa_func, or_, select
from sqlalchemy.orm import Session

from src.models.wallet import (
    TransactionDirection,
    Wallet,
    WalletTransaction,
)
from src.models.xbox import XboxSaleRecord


def _day_range(target_date: date) -> tuple[datetime, datetime]:
    """某天的 [00:00, 次日 00:00) naive 时间范围。"""
    start = datetime.combine(target_date, time.min)
    end = start + timedelta(days=1)
    return start, end


def _collect_leaf_descendants(session: Session, wallet_id: int) -> list[int]:
    """递归取该钱包下所有非 group 的子孙钱包 id。叶子返回 [self]。"""
    wallet = session.get(Wallet, wallet_id)
    if wallet is None:
        return []
    is_group = bool(wallet.is_group)
    if not is_group:
        return [wallet_id]
    out: list[int] = []
    children = list(session.scalars(select(Wallet).where(Wallet.parent_id == wallet_id)))
    for child in children:
        out.extend(_collect_leaf_descendants(session, child.id))
    return out


def _receivable_total_for_wallet_day(
    session: Session, wallet_id: int, target_date: date
) -> Decimal:
    """该钱包当天的"应收"(销售记录 sale_price 累计)。

    口径:XboxSaleRecord.wallet_pool_id == wallet_id AND sale_date 落在当天。
    """
    start, end = _day_range(target_date)
    total = session.scalar(
        select(sa_func.coalesce(sa_func.sum(XboxSaleRecord.sale_price), 0)).where(
            XboxSaleRecord.wallet_pool_id == wallet_id,
            XboxSaleRecord.sale_date >= start,
            XboxSaleRecord.sale_date < end,
        )
    )
    return Decimal(str(total or 0))


def _actual_in_total_for_wallet_day(
    session: Session, wallet_id: int, target_date: date
) -> Decimal:
    """该钱包当天的"实收"(真实 IN 流水累计)。

    group 钱包递归汇总子孙叶子流水。优先用 business_date,fallback created_at。
    """
    leaf_ids = _collect_leaf_descendants(session, wallet_id)
    if not leaf_ids:
        return Decimal("0")

    start, end = _day_range(target_date)
    total = session.scalar(
        select(sa_func.coalesce(sa_func.sum(WalletTransaction.amount), 0)).where(
            WalletTransaction.wallet_id.in_(leaf_ids),
            WalletTransaction.direction == TransactionDirection.IN.value,
            or_(
                WalletTransaction.business_date == target_date,
                and_(
                    WalletTransaction.business_date.is_(None),
                    WalletTransaction.created_at >= start,
                    WalletTransaction.created_at < end,
                ),
            ),
        )
    )
    return Decimal(str(total or 0))


def get_reconcile_report_for_day(
    session: Session,
    target_date: date,
) -> list[dict]:
    """对账报告(新口径,#134):按真实钱包逐行展示当天 应收 vs 实收 vs 差异。

    遍历当天所有有销售记录的 wallet_pool_id(去重),每个钱包一行。
    钱包未 deleted 在前,deleted=true(老订单挂的已废弃理论钱包)在后。

    返回结构:
        [
          {
            "wallet": {"id": int, "name": str, "currency": str,
                       "isGroup": bool, "deleted": bool},
            "receivableTotal": "X.XX",  # 应收
            "actualInTotal":   "X.XX",  # 实收
            "diff":            "X.XX",  # 实收 - 应收
          },
          ...
        ]
    """
    start, end = _day_range(target_date)

    # 取当天所有有销售记录的 wallet_pool_id(去重)
    rows = session.execute(
        select(XboxSaleRecord.wallet_pool_id)
        .where(XboxSaleRecord.sale_date >= start, XboxSaleRecord.sale_date < end)
        .distinct()
    ).all()
    pool_ids = [r[0] for r in rows]

    if not pool_ids:
        return []

    # 拿钱包元信息
    wallets = list(session.scalars(select(Wallet).where(Wallet.id.in_(pool_ids))))
    wallets_by_id = {w.id: w for w in wallets}

    report: list[dict] = []
    for pid in pool_ids:
        w = wallets_by_id.get(pid)
        if w is None:
            continue
        receivable = _receivable_total_for_wallet_day(session, pid, target_date)
        actual_in = _actual_in_total_for_wallet_day(session, pid, target_date)
        currency = w.currency.value if hasattr(w.currency, "value") else w.currency
        report.append({
            "wallet": {
                "id": w.id,
                "name": w.name,
                "currency": currency,
                "isGroup": bool(w.is_group),
                "deleted": w.deleted_at is not None,
            },
            "receivableTotal": str(receivable),
            "actualInTotal": str(actual_in),
            "diff": str(actual_in - receivable),
        })

    # 排序: 未 deleted 在前(按 id 升序), deleted 在后
    report.sort(key=lambda r: (r["wallet"]["deleted"], r["wallet"]["id"]))
    return report


# ---- 兼容旧路由的 stub(对账映射 已废弃,#134) ----


def list_mappings(session: Session) -> list:
    """[deprecated #134] 对账映射已废弃, 永远返回空列表。"""
    return []


def create_mapping(*args, **kwargs):
    raise ValueError("对账映射已废弃(CEO 2026-05-20 #134),客服直选真实钱包不再需要映射")


def delete_mapping(session: Session, mapping_id: int) -> bool:
    return False
