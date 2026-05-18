"""XBOX 对账服务（CEO 2026-05-08 Q1A+Q2A+Q3A+Q4A）。

业务模型：
- 「XBOX 销售归口」（理论值）9 个钱包：丙火网络/兔仔电玩/小小电玩/银行卡A/银行卡B/
  袋鼠8591/喵喵8591/存余额/TOM支付宝
- 「淘宝/台湾/RMB」（实际值）从千牛 / 业务真实流水产生的钱包
- 客服在 XBOX 录入销售时主观选"出售渠道",可能填错
- 对账：每天比对理论流入 vs 实际流入,差异 = 客服填错出售渠道,
  CEO 通过"拆单"功能纠错（已转销售订单改备注模板）

口径（CEO 2026-05-08 确认）：
- Q1A: 一对多映射,CEO 维护对应表
- Q2A: 按日比较（特定 sale_date / IN 流水当天）
- Q3A: 实际值取"当天 IN 流水总额"（不是余额,不是净额）
- Q4A: 仅展示差异,CEO 自己拆单纠错
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import and_, func as sa_func, select
from sqlalchemy.orm import Session

from src.models.wallet import (
    TransactionDirection,
    Wallet,
    WalletTransaction,
    WalletType,
)
from src.models.xbox import XboxRefund, XboxReconcileMapping, XboxSaleRecord


def list_mappings(session: Session) -> list[XboxReconcileMapping]:
    return list(
        session.scalars(select(XboxReconcileMapping).order_by(XboxReconcileMapping.id))
    )


def create_mapping(
    session: Session,
    *,
    theoretical_wallet_id: int,
    actual_wallet_id: int,
) -> XboxReconcileMapping:
    """新建对账映射。校验：
    - 两个钱包都存在
    - 理论值必须是 XBOX_SALES_LEDGER 大类 + 非 group(叶子)
    - 实际值不能是 XBOX_SALES_LEDGER 大类（自己映射自己没意义）
    - 实际值可以是 group 钱包(对账时会递归汇总子钱包流水)
    - 币种必须一致
    - 不重复
    """
    theoretical = session.get(Wallet, theoretical_wallet_id)
    if theoretical is None:
        raise ValueError(f"理论值钱包 {theoretical_wallet_id} 不存在")
    actual = session.get(Wallet, actual_wallet_id)
    if actual is None:
        raise ValueError(f"实际值钱包 {actual_wallet_id} 不存在")

    th_type = theoretical.type.value if hasattr(theoretical.type, "value") else theoretical.type
    ac_type = actual.type.value if hasattr(actual.type, "value") else actual.type
    if th_type != WalletType.XBOX_SALES_LEDGER.value:
        raise ValueError("理论值钱包必须属于 XBOX_SALES_LEDGER 大类")
    if theoretical.is_group:
        raise ValueError("理论值钱包必须是叶子,不能是 group")
    if ac_type == WalletType.XBOX_SALES_LEDGER.value:
        raise ValueError("实际值钱包不能也是 XBOX_SALES_LEDGER 大类")

    th_curr = theoretical.currency.value if hasattr(theoretical.currency, "value") else theoretical.currency
    ac_curr = actual.currency.value if hasattr(actual.currency, "value") else actual.currency
    if th_curr != ac_curr:
        raise ValueError(
            f"币种不一致：理论 {th_curr} ≠ 实际 {ac_curr}"
        )

    existing = session.scalar(
        select(XboxReconcileMapping).where(
            XboxReconcileMapping.theoretical_wallet_id == theoretical_wallet_id,
            XboxReconcileMapping.actual_wallet_id == actual_wallet_id,
        )
    )
    if existing is not None:
        raise ValueError("该映射已存在")

    mapping = XboxReconcileMapping(
        theoretical_wallet_id=theoretical_wallet_id,
        actual_wallet_id=actual_wallet_id,
    )
    session.add(mapping)
    session.flush()
    return mapping


def delete_mapping(session: Session, mapping_id: int) -> bool:
    mapping = session.get(XboxReconcileMapping, mapping_id)
    if mapping is None:
        return False
    session.delete(mapping)
    session.flush()
    return True


def _day_range(target_date: date) -> tuple[datetime, datetime]:
    """某天的 [00:00, 次日 00:00) naive 时间范围（与 created_at 同语义）。"""
    start = datetime.combine(target_date, time.min)
    end = start + timedelta(days=1)
    return start, end


def _theoretical_total_for_day(
    session: Session,
    theoretical_wallet_id: int,
    target_date: date,
) -> Decimal:
    """理论值钱包在指定日期的"流入总额"。

    数据来源：``XboxSaleRecord``。
    - sale_date 落在 target_date 当天 [00:00, 次日 00:00)
      且 wallet_pool_id == theoretical_wallet_id
    - 直接 sum(sale_price)（合单后的最新值）

    CEO 2026-05-12: sale_date 升级为 datetime,所以按当天 datetime 范围筛而不是相等。

    注意: 不是从 wallet_transactions 取(那里有合单调整流水会重复算)。
    """
    start, end = _day_range(target_date)
    total = session.scalar(
        select(sa_func.coalesce(sa_func.sum(XboxSaleRecord.sale_price), 0)).where(
            XboxSaleRecord.wallet_pool_id == theoretical_wallet_id,
            XboxSaleRecord.sale_date >= start,
            XboxSaleRecord.sale_date < end,
        )
    )
    return Decimal(str(total or 0))


def _collect_leaf_descendants(session: Session, wallet_id: int) -> list[int]:
    """递归取该钱包下所有非 group 的子孙钱包 id。

    若 wallet 是叶子,返回 [wallet_id]。
    若 wallet 是 group,递归收集所有非 group 子孙。
    """
    wallet = session.get(Wallet, wallet_id)
    if wallet is None:
        return []
    is_group = bool(wallet.is_group)
    if not is_group:
        return [wallet_id]
    # 递归子孙
    out: list[int] = []
    children = list(
        session.scalars(select(Wallet).where(Wallet.parent_id == wallet_id))
    )
    for child in children:
        out.extend(_collect_leaf_descendants(session, child.id))
    return out


def _actual_total_for_day(
    session: Session,
    actual_wallet_id: int,
    target_date: date,
) -> Decimal:
    """实际值钱包在指定日期的"IN 流水总额"。

    若 actual_wallet 是 group(店铺总钱包),递归汇总所有子孙叶子的当日 IN 流水。

    数据来源：``WalletTransaction``。
    - direction == "in"
    - business_date == target_date 或 created_at 落在当天

    优先用 business_date,fallback created_at（与"日汇总"端点逻辑一致）。
    """
    from sqlalchemy import or_

    leaf_ids = _collect_leaf_descendants(session, actual_wallet_id)
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


def _theoretical_out_total_for_day(
    session: Session,
    theoretical_wallet_id: int,
    target_date: date,
) -> Decimal:
    """理论值钱包在指定日期的"OUT 总额"(退款方向)。

    数据来源：``XboxRefund``(Issue #130)。
    - theoretical_wallet_id 匹配
    - business_date == target_date (退款单的业务日, NULL 时不参与)

    CEO 2026-05-18: 退款的理论 OUT 自动体现在对账页 —
    原销售记录关联的理论钱包当日 OUT vs 实际退款钱包当日 OUT 撞账.
    """
    total = session.scalar(
        select(sa_func.coalesce(sa_func.sum(XboxRefund.refund_amount), 0)).where(
            XboxRefund.theoretical_wallet_id == theoretical_wallet_id,
            XboxRefund.business_date == target_date,
        )
    )
    return Decimal(str(total or 0))


def _actual_out_total_for_day(
    session: Session,
    actual_wallet_id: int,
    target_date: date,
) -> Decimal:
    """实际值钱包在指定日期的"OUT 流水总额"(退款方向)。

    若 actual_wallet 是 group(店铺总钱包),递归汇总所有子孙叶子的当日 OUT 流水。

    数据来源：``WalletTransaction``。
    - direction == "out"
    - business_date == target_date 或 created_at 落在当天
    - **transfer_id IS NULL**(排除划转产生的 OUT, Issue #129)

    优先用 business_date,fallback created_at(与 IN 方向逻辑对称)。
    """
    from sqlalchemy import or_

    leaf_ids = _collect_leaf_descendants(session, actual_wallet_id)
    if not leaf_ids:
        return Decimal("0")

    start, end = _day_range(target_date)
    total = session.scalar(
        select(sa_func.coalesce(sa_func.sum(WalletTransaction.amount), 0)).where(
            WalletTransaction.wallet_id.in_(leaf_ids),
            WalletTransaction.direction == TransactionDirection.OUT.value,
            WalletTransaction.transfer_id.is_(None),
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
    """对账报告：每个有映射的理论值钱包一行,含理论金额、实际金额（合计映射钱包）、差异。

    返回结构(Issue #130 起加 OUT 三字段)：
        [
          {
            "theoreticalWallet": {id, name, currency},
            "actualWallets": [{id, name, currency, total: "X.XX", outTotal: "X.XX"}],
            "theoreticalTotal": "X.XX",        # IN 方向(销售)
            "actualTotal": "X.XX",
            "diff": "X.XX",
            "theoreticalOutTotal": "X.XX",     # OUT 方向(退款) Issue #130
            "actualOutTotal": "X.XX",
            "outDiff": "X.XX",
          },
          ...
        ]
    """
    # 取所有理论值钱包(XBOX_SALES_LEDGER 类下,非 group)
    theoretical_wallets = list(
        session.scalars(
            select(Wallet)
            .where(
                Wallet.type == WalletType.XBOX_SALES_LEDGER.value,
                Wallet.is_group.is_(False),
                Wallet.deleted_at.is_(None),
            )
            .order_by(Wallet.id)
        )
    )

    # 取所有映射
    mappings = list_mappings(session)
    actual_ids_by_theoretical: dict[int, list[int]] = {}
    for m in mappings:
        actual_ids_by_theoretical.setdefault(m.theoretical_wallet_id, []).append(
            m.actual_wallet_id
        )

    # 取所有涉及的实际值钱包
    all_actual_ids = {a for ids in actual_ids_by_theoretical.values() for a in ids}
    actual_wallets_by_id = {
        w.id: w
        for w in session.scalars(select(Wallet).where(Wallet.id.in_(all_actual_ids)))
    } if all_actual_ids else {}

    report: list[dict] = []
    for tw in theoretical_wallets:
        actual_ids = actual_ids_by_theoretical.get(tw.id, [])
        theoretical_total = _theoretical_total_for_day(session, tw.id, target_date)
        theoretical_out_total = _theoretical_out_total_for_day(session, tw.id, target_date)
        actual_details: list[dict] = []
        actual_total = Decimal("0")
        actual_out_total = Decimal("0")
        for aid in actual_ids:
            aw = actual_wallets_by_id.get(aid)
            if aw is None:
                continue
            sub_total = _actual_total_for_day(session, aid, target_date)
            sub_out_total = _actual_out_total_for_day(session, aid, target_date)
            actual_total += sub_total
            actual_out_total += sub_out_total
            actual_details.append({
                "id": aid,
                "name": aw.name,
                "currency": aw.currency.value if hasattr(aw.currency, "value") else aw.currency,
                "total": str(sub_total),
                "outTotal": str(sub_out_total),
            })

        report.append({
            "theoreticalWallet": {
                "id": tw.id,
                "name": tw.name,
                "currency": tw.currency.value if hasattr(tw.currency, "value") else tw.currency,
            },
            "actualWallets": actual_details,
            "theoreticalTotal": str(theoretical_total),
            "actualTotal": str(actual_total),
            "diff": str(theoretical_total - actual_total),
            "theoreticalOutTotal": str(theoretical_out_total),
            "actualOutTotal": str(actual_out_total),
            "outDiff": str(theoretical_out_total - actual_out_total),
        })
    return report
