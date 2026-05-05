"""千牛 Excel 导入与订单 reconcile 业务逻辑。

模块职责：
1. 解析 .xlsx 文件 → 标准化结构化行
2. 按 9 个字段 / 5 状态映射 / 2 支付方式 / 2 店铺类型分流入账
3. 老订单状态变化 reconcile（撤旧流水 + 建新流水）
4. 单一事务原子（异常由调用方 rollback）
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from io import BytesIO
from typing import BinaryIO, Optional

from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.taobao import (
    TaobaoOrder,
    TaobaoOrderPaymentMethod,
    TaobaoOrderStatus,
    TaobaoShop,
)
from src.models.wallet import (
    TransactionDirection,
    Wallet,
    WalletTransaction,
    credit,
    debit,
)


# 千牛导出 Excel 的标准表头（前 9 列），多 1 列、少 1 列、列名错都视为结构错
EXPECTED_HEADERS: tuple[str, ...] = (
    "订单编号",
    "支付单号",
    "支付详情",
    "买家实付金额",
    "订单状态",
    "订单付款时间",
    "店铺名称",
    "发货时间",
    "确认收货打款金额",
)

# 千牛订单状态字面值（用 strip 后与 dict key 对齐）
QIANNIU_STATUS_PENDING_PAY = "等待买家付款"
QIANNIU_STATUS_PAID_UNSHIPPED = "买家已付款,等待卖家发货"
QIANNIU_STATUS_PAID_UNSHIPPED_ALT = "买家已付款，等待卖家发货"  # 全角逗号兜底
QIANNIU_STATUS_SHIPPED_UNCONFIRMED = "卖家已发货，等待买家确认"
QIANNIU_STATUS_SHIPPED_UNCONFIRMED_ALT = "卖家已发货,等待买家确认"  # 半角逗号兜底
QIANNIU_STATUS_RECEIVED = "交易成功"
QIANNIU_STATUS_CLOSED = "交易关闭"

# 微信冻结成熟天数
WECHAT_MATURE_DAYS = 7


class TaobaoImportError(Exception):
    """文件级错误（结构 / 类型）。路由层翻译为 400/404。"""


@dataclass
class ImportReport:
    """导入报告 —— 路由层 by_alias 序列化为 camelCase。"""

    shop_name: str
    total_rows_parsed: int = 0
    created_orders: int = 0
    status_changed_orders: int = 0
    closed_reverted: int = 0
    skipped_no_change: int = 0
    skipped_unpaid_or_unshipped: int = 0
    skipped_unknown_payment: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass
class ParsedRow:
    """单行解析结果。

    ``system_status``/``payment_method`` 为 None 表示"应跳过"（未付款 / 未知支付）。
    """

    row_index: int  # Excel 行号（1-based，第 1 行表头跳过，数据从 2 起）
    order_number: str
    payment_no: str
    payment_detail_raw: str
    buyer_paid_amount: Decimal
    qianniu_status: str
    paid_at: Optional[datetime]
    shop_name_in_row: str
    shipped_at: Optional[datetime]
    confirmed_amount: Decimal
    payment_method: Optional[TaobaoOrderPaymentMethod]
    system_status: Optional[TaobaoOrderStatus]
    is_pending_pay_or_unshipped: bool
    is_unknown_payment: bool


def _to_decimal(value) -> Decimal:
    """空值 / 字符串金额 → Decimal。空字符串当 0。"""
    if value is None or value == "":
        return Decimal("0")
    return Decimal(str(value))


def _to_datetime(value) -> Optional[datetime]:
    """openpyxl 单元格 → datetime。允许空（千牛未发货时 shipped_at 为空）。"""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    # 字符串兜底（一般应被 openpyxl 自动转 datetime,但样例 JSON 是字符串）
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _detect_payment_method(payment_detail: str) -> Optional[TaobaoOrderPaymentMethod]:
    """从 ``支付详情`` 字符串识别支付方式。"""
    if not payment_detail:
        return None
    if "微信支付" in payment_detail:
        return TaobaoOrderPaymentMethod.WECHAT
    if "支付宝" in payment_detail:
        return TaobaoOrderPaymentMethod.ALIPAY
    return None


def _map_status(qianniu_status: str) -> tuple[Optional[TaobaoOrderStatus], bool]:
    """千牛状态 → (系统状态, is_pending_or_unshipped)。

    返回 (None, True)  : 等待买家付款 / 买家已付款等待发货 → 跳过且计入 unpaid_or_unshipped
    返回 (status, False): 三个会落地的状态 (shipped_unconfirmed/received/closed)
    返回 (None, False): 完全未知状态（不应发生，作为 errors）
    """
    s = qianniu_status.strip() if qianniu_status else ""
    if s == QIANNIU_STATUS_PENDING_PAY:
        return None, True
    if s in (QIANNIU_STATUS_PAID_UNSHIPPED, QIANNIU_STATUS_PAID_UNSHIPPED_ALT):
        return None, True
    if s in (QIANNIU_STATUS_SHIPPED_UNCONFIRMED, QIANNIU_STATUS_SHIPPED_UNCONFIRMED_ALT):
        return TaobaoOrderStatus.SHIPPED_UNCONFIRMED, False
    if s == QIANNIU_STATUS_RECEIVED:
        return TaobaoOrderStatus.RECEIVED, False
    if s == QIANNIU_STATUS_CLOSED:
        return TaobaoOrderStatus.CLOSED, False
    return None, False  # 未知状态


def parse_workbook(file_obj: BinaryIO) -> list[list]:
    """读取 .xlsx → 第一工作表所有行（含表头）。

    校验：
    1. 必须能被 openpyxl 打开（否则 TaobaoImportError）
    2. 第 1 行（表头）前 9 列必须等于 EXPECTED_HEADERS
    """
    try:
        wb = load_workbook(file_obj, read_only=True, data_only=True)
    except Exception as exc:  # openpyxl 内部多种异常,统一翻译
        raise TaobaoImportError(f"无法解析 .xlsx 文件: {exc}") from exc

    sheet = wb.active
    if sheet is None:
        raise TaobaoImportError("Excel 文件没有可用工作表")

    rows = list(sheet.iter_rows(values_only=True))
    if not rows:
        raise TaobaoImportError("Excel 文件为空")

    header = rows[0]
    if len(header) < len(EXPECTED_HEADERS):
        raise TaobaoImportError(
            f"Excel 列数不足，期望前 {len(EXPECTED_HEADERS)} 列为 {EXPECTED_HEADERS}"
        )
    actual_first_n = tuple((str(c).strip() if c is not None else "") for c in header[: len(EXPECTED_HEADERS)])
    if actual_first_n != EXPECTED_HEADERS:
        raise TaobaoImportError(
            f"Excel 表头不符，期望 {EXPECTED_HEADERS}，实际 {actual_first_n}"
        )

    return rows


def _parse_row(row_index: int, row: tuple) -> ParsedRow:
    """单行 → ParsedRow（不做 DB 操作）。"""
    # 取前 9 列；不够列时 IndexError 会暴露在 errors
    order_number = str(row[0]).strip() if row[0] is not None else ""
    payment_no = str(row[1]).strip() if row[1] is not None else ""
    payment_detail_raw = str(row[2]) if row[2] is not None else ""
    buyer_paid_amount = _to_decimal(row[3])
    qianniu_status_raw = str(row[4]).strip() if row[4] is not None else ""
    paid_at = _to_datetime(row[5])
    shop_name_in_row = str(row[6]).strip() if row[6] is not None else ""
    shipped_at = _to_datetime(row[7])
    confirmed_amount = _to_decimal(row[8])

    payment_method = _detect_payment_method(payment_detail_raw)
    system_status, is_pending_or_unshipped = _map_status(qianniu_status_raw)
    is_unknown_payment = payment_method is None and not is_pending_or_unshipped and system_status is not None
    # 注意：is_unknown_payment 仅在状态会落地时才追究支付方式

    return ParsedRow(
        row_index=row_index,
        order_number=order_number,
        payment_no=payment_no,
        payment_detail_raw=payment_detail_raw,
        buyer_paid_amount=buyer_paid_amount,
        qianniu_status=qianniu_status_raw,
        paid_at=paid_at,
        shop_name_in_row=shop_name_in_row,
        shipped_at=shipped_at,
        confirmed_amount=confirmed_amount,
        payment_method=payment_method,
        system_status=system_status,
        is_pending_pay_or_unshipped=is_pending_or_unshipped,
        is_unknown_payment=is_unknown_payment,
    )


def _resolve_target_wallet(
    shop: TaobaoShop,
    payment_method: TaobaoOrderPaymentMethod,
    system_status: TaobaoOrderStatus,
) -> Optional[int]:
    """三维分流（支付方式 × 系统状态 × 店铺类型）→ 目标钱包 id。

    返回 None 表示该状态不入账（如 closed）。

    分流矩阵：
    - alipay/shipped_unconfirmed → unconfirmed_alipay  (A/B 一致)
    - alipay/received            → A 类: payment_wallet  | B 类: bank_card
    - wechat/shipped_unconfirmed → unconfirmed_wechat  (A/B 一致)
    - wechat/received            → aggregator_frozen   (A/B 一致;聚合支付独立于店铺归属)
    - closed                     → None (不入账)
    """
    if system_status == TaobaoOrderStatus.CLOSED:
        return None

    is_b_type = shop.payment_wallet_id is None  # 兔仔电玩

    if payment_method == TaobaoOrderPaymentMethod.ALIPAY:
        if system_status == TaobaoOrderStatus.SHIPPED_UNCONFIRMED:
            return shop.unconfirmed_alipay_wallet_id
        if system_status == TaobaoOrderStatus.RECEIVED:
            if is_b_type:
                return shop.bank_card_wallet_id  # 兔仔停在银行卡
            return shop.payment_wallet_id
    elif payment_method == TaobaoOrderPaymentMethod.WECHAT:
        if system_status == TaobaoOrderStatus.SHIPPED_UNCONFIRMED:
            return shop.unconfirmed_wechat_wallet_id
        if system_status == TaobaoOrderStatus.RECEIVED:
            return shop.aggregator_frozen_wallet_id
    return None


def _amount_for_status(parsed: ParsedRow) -> Decimal:
    """按状态选金额：received 用确认收货金额；shipped_unconfirmed 用买家实付。"""
    if parsed.system_status == TaobaoOrderStatus.RECEIVED:
        return parsed.confirmed_amount
    if parsed.system_status == TaobaoOrderStatus.SHIPPED_UNCONFIRMED:
        return parsed.buyer_paid_amount
    return Decimal("0")


def _credit_for_row(
    session: Session,
    shop: TaobaoShop,
    parsed: ParsedRow,
    wallet_id: int,
    amount: Decimal,
) -> WalletTransaction:
    """按规则 credit。微信/received 写 mature_at = received_at + 7d。"""
    mature_at: Optional[datetime] = None
    if (
        parsed.payment_method == TaobaoOrderPaymentMethod.WECHAT
        and parsed.system_status == TaobaoOrderStatus.RECEIVED
    ):
        # received_at 优先用 shipped_at（同一行的 "发货时间"），缺失则用 paid_at；都缺则 now()
        base = parsed.shipped_at or parsed.paid_at or datetime.now()
        mature_at = base + timedelta(days=WECHAT_MATURE_DAYS)
    remark = f"千牛订单 #{parsed.order_number} {parsed.system_status.value}"
    return credit(
        session,
        wallet_id,
        amount,
        remark=remark,
        mature_at=mature_at,
    )


def _debit_old_tx(
    session: Session,
    order: TaobaoOrder,
    reason: str,
) -> None:
    """根据 ``order.bookkeeping_tx_id`` 找老流水的 amount，从老钱包 debit 同金额。

    若 bookkeeping_tx_id / wallet_id 任一缺失，跳过（视为之前未入账）。
    """
    if order.bookkeeping_tx_id is None or order.bookkeeping_wallet_id is None:
        return
    old_tx = session.get(WalletTransaction, order.bookkeeping_tx_id)
    if old_tx is None:
        return
    debit(
        session,
        order.bookkeeping_wallet_id,
        Decimal(old_tx.amount),
        remark=f"reconcile #{order.order_number} {reason}",
    )


def import_qianniu_workbook(
    session: Session,
    shop: TaobaoShop,
    file_obj: BinaryIO,
) -> ImportReport:
    """主入口：解析 + 入账 + reconcile，返回 ImportReport。

    调用方负责 commit / rollback。本函数只 add + flush，**不 commit**。
    任何 SQLAlchemy 异常会向上抛，调用方应 rollback。
    """
    rows = parse_workbook(file_obj)
    report = ImportReport(shop_name=shop.name)

    for row_index, raw_row in enumerate(rows[1:], start=2):
        report.total_rows_parsed += 1
        try:
            parsed = _parse_row(row_index, raw_row)
        except Exception as exc:
            report.errors.append(f"行 {row_index} 解析异常: {exc}")
            continue

        # 跳过未付款 / 未发货
        if parsed.is_pending_pay_or_unshipped:
            report.skipped_unpaid_or_unshipped += 1
            continue

        # 状态完全未识别（理论不应发生）
        if parsed.system_status is None:
            report.errors.append(
                f"行 {row_index} 订单 {parsed.order_number} 未识别千牛状态: {parsed.qianniu_status!r}"
            )
            continue

        # 支付方式未知（仅当状态会落地时才追究）
        if parsed.is_unknown_payment:
            report.skipped_unknown_payment += 1
            continue

        # 此处 system_status ∈ {shipped_unconfirmed, received, closed}
        existing = session.scalar(
            select(TaobaoOrder).where(TaobaoOrder.order_number == parsed.order_number)
        )

        if existing is None:
            _handle_new_order(session, shop, parsed, report)
        else:
            _handle_existing_order(session, shop, existing, parsed, report)

    return report


def _handle_new_order(
    session: Session,
    shop: TaobaoShop,
    parsed: ParsedRow,
    report: ImportReport,
) -> None:
    """情况 1：新订单。

    - closed：不入账，但仍记一行 TaobaoOrder（status=closed, bookkeeping=None）
    - 其他：按状态入账
    """
    amount = _amount_for_status(parsed)
    wallet_id = _resolve_target_wallet(shop, parsed.payment_method, parsed.system_status)

    bookkeeping_wallet_id: Optional[int] = None
    bookkeeping_tx_id: Optional[int] = None

    if parsed.system_status != TaobaoOrderStatus.CLOSED and wallet_id is not None and amount > 0:
        tx = _credit_for_row(session, shop, parsed, wallet_id, amount)
        bookkeeping_wallet_id = wallet_id
        bookkeeping_tx_id = tx.id

    received_at = parsed.shipped_at if parsed.system_status == TaobaoOrderStatus.RECEIVED else None

    order = TaobaoOrder(
        shop_id=shop.id,
        order_number=parsed.order_number,
        payment_method=parsed.payment_method.value,
        amount=amount,
        status=parsed.system_status.value,
        bookkeeping_wallet_id=bookkeeping_wallet_id,
        bookkeeping_tx_id=bookkeeping_tx_id,
        shipped_at=parsed.shipped_at,
        received_at=received_at,
    )
    session.add(order)
    session.flush()

    if parsed.system_status == TaobaoOrderStatus.CLOSED:
        # 新进来就 closed,不算 closed_reverted（因从未入过账）
        report.created_orders += 1
    else:
        report.created_orders += 1


def _handle_existing_order(
    session: Session,
    shop: TaobaoShop,
    order: TaobaoOrder,
    parsed: ParsedRow,
    report: ImportReport,
) -> None:
    """情况 2/3/4/5：老订单。

    2: status 没变 → 仅更新 last_synced_at
    3/5: status 变了（包括跳级）→ 撤老流水 + 入新账
    4: 变 closed → 撤老流水 + 不入新账
    """
    old_status_value = order.status.value if hasattr(order.status, "value") else order.status

    if old_status_value == parsed.system_status.value:
        # 情况 2：无变化
        order.last_synced_at = datetime.now()
        report.skipped_no_change += 1
        return

    # 状态发生变化
    if parsed.system_status == TaobaoOrderStatus.CLOSED:
        # 情况 4：变 closed
        _debit_old_tx(session, order, "状态变为关闭")
        order.status = TaobaoOrderStatus.CLOSED.value
        order.bookkeeping_wallet_id = None
        order.bookkeeping_tx_id = None
        order.last_synced_at = datetime.now()
        report.closed_reverted += 1
        return

    # 情况 3/5：变到另一个会落地的状态
    _debit_old_tx(session, order, "状态变化")

    new_amount = _amount_for_status(parsed)
    new_wallet_id = _resolve_target_wallet(shop, parsed.payment_method, parsed.system_status)

    new_tx_id: Optional[int] = None
    if new_wallet_id is not None and new_amount > 0:
        new_tx = _credit_for_row(session, shop, parsed, new_wallet_id, new_amount)
        new_tx_id = new_tx.id

    order.status = parsed.system_status.value
    order.amount = new_amount
    order.bookkeeping_wallet_id = new_wallet_id if new_tx_id is not None else None
    order.bookkeeping_tx_id = new_tx_id
    order.last_synced_at = datetime.now()
    if parsed.system_status == TaobaoOrderStatus.RECEIVED:
        order.received_at = parsed.shipped_at or order.received_at
    if parsed.shipped_at is not None:
        order.shipped_at = parsed.shipped_at

    report.status_changed_orders += 1
