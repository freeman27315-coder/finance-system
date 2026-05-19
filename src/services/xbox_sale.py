"""XBOX 销售记录服务（FR-06 合单 + FR-07 资金池流入）。

业务规则（CEO 2026-05-08 确认）：
- 合单：同账号 + 同 wallet_item_id → 视为同一销售记录,售价相加
- 销售记录创建即 credit ``sale_price`` 到 ``wallet_pool_id``（Q2A）
- 改 sale_price → 资金池 diff 调整(Q2A)
- 改 wallet_pool_id → 旧池 debit + 新池 credit(Q3A)
- 不能撤销但可改字段（CEO 4B）
- sale_currency 必须和 wallet_pool 钱包 currency 一致

所有变更都通过 ``Wallet.balance`` 加减 + 写 ``WalletTransaction`` 流水。
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional, Union

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.wallet import (
    TransactionDirection,
    Wallet,
    WalletTransaction,
    credit,
    debit,
)
from src.models.xbox import (
    XboxAccount,
    XboxChangeLog,
    XboxOrder,
    XboxOrderStatus,
    XboxSaleRecord,
    XboxWalletItem,
)
from src.utils.time import china_now


def _log_change(
    session: Session,
    entity_type: str,
    entity_id: int,
    action: str,
    detail: str,
    operator: str = "manual",
) -> None:
    """写一条变更日志（CEO Q3:A 订单/销售记录审计）。"""
    log = XboxChangeLog(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        detail=detail,
        operator=operator,
    )
    session.add(log)
    session.flush()


# 币种 → 钱包应该的 currency
CURRENCY_TO_WALLET_CURRENCY = {
    "CNY": "CNY",
    "USD": "USD",
    "USDT": "USDT",
    "TWD": "TWD",
}


def _validate_pool_currency(session: Session, wallet_pool_id: int, sale_currency: str) -> Wallet:
    """校验资金池钱包存在且币种与 sale_currency 一致。返回钱包对象。"""
    wallet = session.get(Wallet, wallet_pool_id)
    if wallet is None:
        raise ValueError(f"资金池钱包 {wallet_pool_id} 不存在")
    expected = CURRENCY_TO_WALLET_CURRENCY.get(sale_currency)
    if expected is None:
        raise ValueError(f"不支持的销售币种: {sale_currency}")
    actual = wallet.currency.value if hasattr(wallet.currency, "value") else wallet.currency
    if actual != expected:
        raise ValueError(
            f"资金池钱包币种 {actual} 与销售币种 {sale_currency} 不一致"
        )
    return wallet


def _find_existing_sale_record(
    session: Session,
    account_id: int,
    wallet_item_id: int,
) -> Optional[XboxSaleRecord]:
    """[legacy] 合单查询：同账号 + 同 wallet_item_id 的现有销售记录。
    新流程改用 _find_existing_sale_record_by_pool。"""
    return session.scalar(
        select(XboxSaleRecord).where(
            XboxSaleRecord.account_id == account_id,
            XboxSaleRecord.wallet_item_id == wallet_item_id,
        )
    )


def _find_existing_sale_record_by_pool(
    session: Session,
    account_id: int,
    wallet_pool_id: int,
) -> Optional[XboxSaleRecord]:
    """#134 新合单查询: 同账号 + 同 wallet_pool_id(真实钱包) 的现有销售记录。"""
    return session.scalar(
        select(XboxSaleRecord).where(
            XboxSaleRecord.account_id == account_id,
            XboxSaleRecord.wallet_pool_id == wallet_pool_id,
        )
    )


def _coerce_sale_datetime(value: Union[date, datetime, None]) -> Optional[datetime]:
    """把 date 自动升 datetime(00:00:00),便于和旧调用方/测试兼容。"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    return value


def create_or_merge_sale_record(
    session: Session,
    *,
    account: XboxAccount,
    sale_date: Union[date, datetime],
    product_name: str,
    operator_name: str,
    sale_price: Decimal,
    sale_currency: str,
    wallet_method_id: Optional[int] = None,
    wallet_item_id: Optional[int] = None,
    wallet_item_label: Optional[str] = None,
    wallet_pool_id: int,
    order: Optional[XboxOrder] = None,
) -> XboxSaleRecord:
    """创建销售记录或合并到现有的（FR-06）。

    CEO 2026-05-20 #134: **不再 credit 真实钱包余额**。销售记录只是"应收"凭证,
    钱包余额由台湾页/资产页的"更新余额"或手动 credit/debit 接口更新。
    撞账逻辑: 真实钱包当天应收(SUM sale_price) vs 实收(钱包真实 IN 流水)。

    合单规则: 同账号 + 同 wallet_pool_id → 视为同一销售记录,累加 sale_price。
    (老规则按 wallet_item_id 合,但新订单 item_id 全 NULL,所以改按 pool_id)

    传入 ``order`` 时,会把订单的 sale_record_id 指向新/旧记录,
    并把订单 status 改成 converted。
    """
    pool = _validate_pool_currency(session, wallet_pool_id, sale_currency)
    sale_price = Decimal(sale_price)
    if sale_price < 0:
        raise ValueError("销售价格不能为负数")

    # 销售日期 → 一律 datetime;有订单时优先取 order.order_at
    sale_dt = _coerce_sale_datetime(sale_date)
    if order is not None and order.order_at is not None:
        # CEO 2026-05-12: 销售日期 = 微软订单抓取时间(中国时区精确到秒)
        sale_dt = order.order_at
    if sale_dt is None:
        raise ValueError("销售日期不能为空")

    # 新订单按 wallet_pool_id 合单(老规则按 wallet_item_id, 新订单 item_id 一律 NULL)
    existing = _find_existing_sale_record_by_pool(session, account.id, wallet_pool_id)

    if existing is None:
        # 新建销售记录(不动钱包余额)
        record = XboxSaleRecord(
            account_id=account.id,
            sale_date=sale_dt,
            product_name=product_name,
            operator_name=operator_name,
            sale_price=sale_price,
            sale_currency=sale_currency,
            wallet_method_id=wallet_method_id,
            wallet_item_id=wallet_item_id,
            wallet_item_label=wallet_item_label or pool.name,
            wallet_pool_id=wallet_pool_id,
        )
        session.add(record)
        session.flush()

        _log_change(
            session,
            "sale_record",
            record.id,
            "created",
            f"售价={sale_price} {sale_currency}, 钱包 wallet#{wallet_pool_id} ({pool.name})",
        )

    else:
        # 合单：累加 sale_price(不动钱包余额)
        if existing.sale_currency != sale_currency:
            raise ValueError(
                f"合单失败：币种不一致(已有 {existing.sale_currency},新 {sale_currency})"
            )
        old_price = Decimal(existing.sale_price)
        new_total = old_price + sale_price
        diff = sale_price  # 新增订单贡献的金额

        existing.sale_price = new_total
        existing.last_updated_at = china_now()

        # 更新 product_name 为合单后追加（保留原来 + 新订单）
        if product_name and product_name not in (existing.product_name or ""):
            existing.product_name = f"{existing.product_name}; {product_name}"

        _log_change(
            session,
            "sale_record",
            existing.id,
            "merged",
            f"合单追加 +{diff} {sale_currency} ({product_name}), 新总额 {new_total}",
        )

        record = existing

    # 关联订单
    if order is not None:
        order.sale_record_id = record.id
        order.status = XboxOrderStatus.CONVERTED.value
        order.last_updated_at = china_now()

    session.flush()
    return record


def update_sale_record_fields(
    session: Session,
    record: XboxSaleRecord,
    *,
    sale_date: Union[date, datetime, None] = None,
    product_name: Optional[str] = None,
    operator_name: Optional[str] = None,
    sale_price: Optional[Decimal] = None,
    sale_currency: Optional[str] = None,
    wallet_method_id: Optional[int] = None,
    wallet_item_id: Optional[int] = None,
    wallet_item_label: Optional[str] = None,
    wallet_pool_id: Optional[int] = None,
) -> XboxSaleRecord:
    """改销售记录字段。自动联动钱包余额（CEO Q2A + Q3A）。

    - 改 sale_price: 资金池 diff 调整
    - 改 wallet_pool_id（或 sale_currency 联动）：旧池 debit + 新池 credit
    """
    now = china_now()

    new_currency = sale_currency if sale_currency is not None else record.sale_currency
    new_pool_id = wallet_pool_id if wallet_pool_id is not None else record.wallet_pool_id
    new_price = Decimal(sale_price) if sale_price is not None else Decimal(record.sale_price)
    if new_price < 0:
        raise ValueError("销售价格不能为负数")

    pool_changed = new_pool_id != record.wallet_pool_id
    currency_changed = new_currency != record.sale_currency
    price_changed = new_price != Decimal(record.sale_price)

    # 校验新池子币种
    if pool_changed or currency_changed:
        _validate_pool_currency(session, new_pool_id, new_currency)

    # CEO 2026-05-20 #134: 改字段不再动真实钱包余额。改的只是"应收"记录,
    # 撞账时按当时的 wallet_pool_id + sale_price 汇总即可。
    if pool_changed or currency_changed:
        old_pool_id = record.wallet_pool_id
        old_currency = record.sale_currency
        old_amount = Decimal(record.sale_price)
        record.wallet_pool_id = new_pool_id
        record.sale_currency = new_currency
        record.sale_price = new_price
        _log_change(
            session,
            "sale_record",
            record.id,
            "wallet_pool_changed",
            f"钱包 wallet#{old_pool_id}({old_currency}) → wallet#{new_pool_id}({new_currency}), 售价 {old_amount} → {new_price}",
        )
    elif price_changed:
        old_price = Decimal(record.sale_price)
        diff = new_price - old_price
        record.sale_price = new_price
        _log_change(
            session,
            "sale_record",
            record.id,
            "updated",
            f"售价 {old_price} → {new_price} ({record.sale_currency}), diff={diff}",
        )

    # 3) 更新其他普通字段
    if sale_date is not None:
        record.sale_date = _coerce_sale_datetime(sale_date) or record.sale_date
    if product_name is not None:
        record.product_name = product_name
    if operator_name is not None:
        record.operator_name = operator_name
    if wallet_method_id is not None:
        record.wallet_method_id = wallet_method_id
    if wallet_item_id is not None:
        record.wallet_item_id = wallet_item_id
    if wallet_item_label is not None:
        record.wallet_item_label = wallet_item_label

    record.last_updated_at = now
    session.flush()
    return record


def _date_range_to_datetime_bounds(
    from_date: Optional[date], to_date: Optional[date]
) -> tuple[Optional[datetime], Optional[datetime]]:
    """把传入的 date 范围转成 datetime 闭区间(用于和 sale_date(datetime)比较):
    [from_date 00:00:00, (to_date+1天) 00:00:00).
    """
    from datetime import timedelta

    lower: Optional[datetime] = None
    upper: Optional[datetime] = None
    if from_date is not None:
        lower = datetime.combine(from_date, datetime.min.time())
    if to_date is not None:
        upper = datetime.combine(to_date, datetime.min.time()) + timedelta(days=1)
    return lower, upper


def list_sale_records(
    session: Session,
    *,
    account_id: Optional[int] = None,
    wallet_pool_id: Optional[int] = None,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
) -> list[XboxSaleRecord]:
    """列销售记录。按 sale_date 闭区间过滤(传 date 时按当天 0 点 ~ 次日 0 点开区间)。"""
    stmt = select(XboxSaleRecord).order_by(XboxSaleRecord.id.desc())
    if account_id is not None:
        stmt = stmt.where(XboxSaleRecord.account_id == account_id)
    if wallet_pool_id is not None:
        stmt = stmt.where(XboxSaleRecord.wallet_pool_id == wallet_pool_id)
    lower, upper = _date_range_to_datetime_bounds(from_date, to_date)
    if lower is not None:
        stmt = stmt.where(XboxSaleRecord.sale_date >= lower)
    if upper is not None:
        stmt = stmt.where(XboxSaleRecord.sale_date < upper)
    return list(session.scalars(stmt))


def get_sales_summary(
    session: Session,
    *,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
) -> dict:
    """销售汇总（按币种 / 收款方式 / 备注模板）。

    返回:
      {
        "totalByCurrency": [{currency: "CNY", total: ¥, count: N}],
        "totalByMethod": [{methodLabel: "淘宝渠道", currency: "CNY", total: ¥, count: N}],
        "totalByItem": [{itemLabel: "丙火网络", currency: "CNY", total: ¥, count: N}],
        "saleRecordCount": N,
        "orderCount": N (含订单数,关联订单总和),
      }
    """
    from sqlalchemy import func as sa_func

    from src.models.xbox import XboxOrder as _XboxOrder
    from src.models.xbox import XboxWalletItem, XboxWalletMethod

    # 销售记录基础筛选(date → datetime 边界)
    base_filters = []
    lower, upper = _date_range_to_datetime_bounds(from_date, to_date)
    if lower is not None:
        base_filters.append(XboxSaleRecord.sale_date >= lower)
    if upper is not None:
        base_filters.append(XboxSaleRecord.sale_date < upper)

    # 按币种汇总
    by_currency_rows = list(
        session.execute(
            select(
                XboxSaleRecord.sale_currency,
                sa_func.sum(XboxSaleRecord.sale_price).label("total"),
                sa_func.count(XboxSaleRecord.id).label("cnt"),
            )
            .where(*base_filters)
            .group_by(XboxSaleRecord.sale_currency)
        )
    )
    by_currency = [
        {"currency": row.sale_currency, "total": str(Decimal(row.total or 0)), "count": int(row.cnt)}
        for row in by_currency_rows
    ]

    # 按收款方式汇总（method 维度）
    by_method_rows = list(
        session.execute(
            select(
                XboxWalletMethod.label.label("method_label"),
                XboxSaleRecord.sale_currency,
                sa_func.sum(XboxSaleRecord.sale_price).label("total"),
                sa_func.count(XboxSaleRecord.id).label("cnt"),
            )
            .select_from(XboxSaleRecord)
            .join(XboxWalletMethod, XboxWalletMethod.id == XboxSaleRecord.wallet_method_id)
            .where(*base_filters)
            .group_by(XboxWalletMethod.label, XboxSaleRecord.sale_currency)
            .order_by(XboxWalletMethod.label)
        )
    )
    by_method = [
        {
            "methodLabel": row.method_label,
            "currency": row.sale_currency,
            "total": str(Decimal(row.total or 0)),
            "count": int(row.cnt),
        }
        for row in by_method_rows
    ]

    # 按备注模板汇总（item 维度）
    by_item_rows = list(
        session.execute(
            select(
                XboxSaleRecord.wallet_item_label.label("item_label"),
                XboxSaleRecord.sale_currency,
                sa_func.sum(XboxSaleRecord.sale_price).label("total"),
                sa_func.count(XboxSaleRecord.id).label("cnt"),
            )
            .where(*base_filters)
            .group_by(XboxSaleRecord.wallet_item_label, XboxSaleRecord.sale_currency)
            .order_by(XboxSaleRecord.wallet_item_label)
        )
    )
    by_item = [
        {
            "itemLabel": row.item_label,
            "currency": row.sale_currency,
            "total": str(Decimal(row.total or 0)),
            "count": int(row.cnt),
        }
        for row in by_item_rows
    ]

    # 销售记录数 + 订单数
    sale_record_count = session.scalar(
        select(sa_func.count(XboxSaleRecord.id)).where(*base_filters)
    ) or 0
    # 订单数 = 与匹配的销售记录关联的订单
    order_count = session.scalar(
        select(sa_func.count(_XboxOrder.id))
        .select_from(_XboxOrder)
        .join(XboxSaleRecord, XboxSaleRecord.id == _XboxOrder.sale_record_id)
        .where(*base_filters)
    ) or 0

    return {
        "totalByCurrency": by_currency,
        "totalByMethod": by_method,
        "totalByItem": by_item,
        "saleRecordCount": int(sale_record_count),
        "orderCount": int(order_count),
    }
