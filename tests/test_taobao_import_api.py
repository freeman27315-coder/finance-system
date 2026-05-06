"""千牛 v2 14 列 Excel 导入 + 订单 reconcile + 状态变化金流 综合测试。

涵盖（issue #84 后）：
- 端点 happy path：新订单 / 老订单 / 状态变化 / 关闭 / 跳过
- 14 列严格表头校验（多 1 列、少 1 列、列名错都视为结构错）
- 三维分流矩阵（A 类 vs B 类 / alipay vs wechat / shipped_unconfirmed vs received）
- 0.6% 手续费规则：仅 received 时扣，net = gross - round(gross*0.006, 2) ROUND_HALF_UP
  边界值：56→0.34、269→1.61、27.50→0.17、100→0.60
- 在途订单 amount=gross；已确认订单 amount=net、gross/fee/confirmed_at 都填值
- 微信/received → aggregator_frozen + mature_at = confirmed_at + 7d；缺失时兜底 shipped_at + 7d
- reconcile：在途→确认（debit gross + credit net，差额=fee 自然消失）
- 状态变成 closed：撤账无新流水
- 错误处理：404 shop / 400 非 .xlsx / 400 表头错
- 跳过未付款 / 未发货 / 未知支付方式
- 单一事务原子性
- 末尾自动解冻：到期流水自动从 frozen → available
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import select

from src import database
from src.main import app
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
)
from src.services.assets import ensure_default_asset_wallets
from src.services.taobao import ensure_default_taobao_wallets


# 千牛 v2 标准 14 列表头
HEADERS = [
    "订单编号",
    "支付单号",
    "支付详情",
    "买家实付金额",
    "订单状态",
    "订单创建时间",
    "订单付款时间",
    "宝贝种类",
    "店铺名称",
    "卖家服务费",
    "退款金额",
    "发货时间",
    "确认收货时间",
    "确认收货打款金额",
]


@pytest.fixture()
def client(tmp_path):
    database.configure_database(f"sqlite:///{tmp_path / 'taobao_import.db'}")
    database.init_db()
    db = database.SessionLocal()
    try:
        ensure_default_asset_wallets(db)
        ensure_default_taobao_wallets(db)
        db.commit()
    finally:
        db.close()
    return TestClient(app)


def _shop_by_name(name: str) -> TaobaoShop:
    db = database.SessionLocal()
    try:
        return db.scalar(select(TaobaoShop).where(TaobaoShop.name == name))
    finally:
        db.close()


def _row(
    *,
    order_no: str,
    payment_no: str,
    payment_detail: str,
    buyer_paid: str,
    status_zh: str,
    paid_at: str = "",
    shop_name: str = "丙火网络",
    shipped_at: str = "",
    confirmed_at: str = "",
    confirmed_amount: str = "0.00",
    created_at: str = "",
    bao_kind: str = "1",
    seller_service_fee: str = "0.00",
    refund_amount: str = "0.00",
) -> list:
    """生成 14 列数据行。col 5/7/9/10 占位（CEO 同意忽略,但表头必须严格）。"""
    return [
        order_no,                                     # col 0  订单编号
        payment_no,                                   # col 1  支付单号
        payment_detail,                               # col 2  支付详情
        buyer_paid,                                   # col 3  买家实付金额
        status_zh,                                    # col 4  订单状态
        created_at or paid_at,                        # col 5  订单创建时间(占位)
        paid_at,                                      # col 6  订单付款时间
        bao_kind,                                     # col 7  宝贝种类(占位)
        shop_name,                                    # col 8  店铺名称
        seller_service_fee,                           # col 9  卖家服务费(占位)
        refund_amount,                                # col 10 退款金额(占位)
        shipped_at,                                   # col 11 发货时间
        confirmed_at,                                 # col 12 确认收货时间
        confirmed_amount,                             # col 13 确认收货打款金额
    ]


def _build_xlsx(rows: list[list], headers: list[str] | None = None) -> bytes:
    """生成包含表头 + 数据行的 .xlsx bytes。"""
    wb = Workbook()
    ws = wb.active
    ws.append(headers if headers is not None else HEADERS)
    for row in rows:
        ws.append(row)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _post_import(client: TestClient, shop_id: int, content: bytes, filename: str = "export.xlsx"):
    return client.post(
        f"/taobao/shops/{shop_id}/import",
        files={
            "file": (
                filename,
                content,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )


def _wechat_detail(payment_no: str, amount: str) -> str:
    return f"支付方式：微信支付，支付单号：{payment_no}，金额：{amount}；"


def _alipay_detail(payment_no: str, amount: str) -> str:
    return f"支付方式：支付宝，支付单号：{payment_no}，金额：{amount}；"


def _wallet_balance(wallet_id: int) -> Decimal:
    db = database.SessionLocal()
    try:
        w = db.get(Wallet, wallet_id)
        return Decimal(w.balance)
    finally:
        db.close()


def _wallet_tx_count(wallet_id: int) -> int:
    db = database.SessionLocal()
    try:
        return len(
            db.scalars(
                select(WalletTransaction).where(WalletTransaction.wallet_id == wallet_id)
            ).all()
        )
    finally:
        db.close()


def _last_tx(wallet_id: int) -> WalletTransaction:
    db = database.SessionLocal()
    try:
        return db.scalars(
            select(WalletTransaction)
            .where(WalletTransaction.wallet_id == wallet_id)
            .order_by(WalletTransaction.id.desc())
        ).first()
    finally:
        db.close()


def _get_order(order_number: str) -> TaobaoOrder:
    db = database.SessionLocal()
    try:
        return db.scalar(
            select(TaobaoOrder).where(TaobaoOrder.order_number == order_number)
        )
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 端点错误路径
# ---------------------------------------------------------------------------


def test_import_404_when_shop_not_found(client):
    content = _build_xlsx([])
    response = _post_import(client, 9999, content)
    assert response.status_code == 404
    assert "店铺" in response.json()["detail"]


def test_import_400_when_not_xlsx(client):
    shop = _shop_by_name("丙火网络")
    response = client.post(
        f"/taobao/shops/{shop.id}/import",
        files={"file": ("export.csv", b"some,csv,data", "text/csv")},
    )
    assert response.status_code == 400
    assert ".xlsx" in response.json()["detail"]


def test_import_400_when_header_wrong_in_middle(client):
    """中间一列改名 → 400 表头错。"""
    shop = _shop_by_name("丙火网络")
    bad_headers = HEADERS.copy()
    bad_headers[7] = "WRONG_COL"  # 把 "宝贝种类" 改错
    content = _build_xlsx([], headers=bad_headers)
    response = _post_import(client, shop.id, content)
    assert response.status_code == 400
    assert "表头" in response.json()["detail"]


def test_import_400_when_columns_too_few(client):
    """少 1 列（13 列）→ 400 列数不足。"""
    shop = _shop_by_name("丙火网络")
    content = _build_xlsx([], headers=HEADERS[:13])
    response = _post_import(client, shop.id, content)
    assert response.status_code == 400


def test_import_400_when_old_v1_9col_header_rejected(client):
    """v1 旧 9 列表头 → 14 列严格校验下应被 400 拒绝。"""
    shop = _shop_by_name("丙火网络")
    old_headers = [
        "订单编号", "支付单号", "支付详情", "买家实付金额", "订单状态",
        "订单付款时间", "店铺名称", "发货时间", "确认收货打款金额",
    ]
    content = _build_xlsx([], headers=old_headers)
    response = _post_import(client, shop.id, content)
    assert response.status_code == 400


def test_import_400_when_row_shop_name_mismatched(client):
    """行内店铺名 != 上传 shop.name → 400 + 错误信息含两个店铺名 + 整体回滚。"""
    shop = _shop_by_name("丙火网络")
    rows = [
        _row(
            order_no="ROW_OK",
            payment_no="PAY_OK",
            payment_detail=_alipay_detail("PAY_OK", "10.00"),
            buyer_paid="10.00",
            status_zh="交易成功",
            paid_at="2026-04-29 23:00:00",
            shop_name="丙火网络",
            shipped_at="2026-04-30 00:00:00",
            confirmed_at="2026-04-30 12:00:00",
            confirmed_amount="10.00",
        ),
        _row(
            order_no="ROW_BAD",
            payment_no="PAY_BAD",
            payment_detail=_alipay_detail("PAY_BAD", "20.00"),
            buyer_paid="20.00",
            status_zh="交易成功",
            paid_at="2026-04-29 23:00:00",
            shop_name="兔仔电玩",  # 不匹配
            shipped_at="2026-04-30 00:00:00",
            confirmed_at="2026-04-30 12:00:00",
            confirmed_amount="20.00",
        ),
    ]
    response = _post_import(client, shop.id, _build_xlsx(rows))
    assert response.status_code == 400, response.text
    detail = response.json()["detail"]
    assert "兔仔电玩" in detail
    assert "丙火网络" in detail

    # 整体回滚
    assert _wallet_balance(shop.store_alipay_wallet_id) == Decimal("0.000000")

    db = database.SessionLocal()
    try:
        orders = db.scalars(select(TaobaoOrder)).all()
        assert orders == []
    finally:
        db.close()


def test_import_400_when_row_shop_name_empty(client):
    """行内店铺名为空 → 视为不匹配 → 400。"""
    shop = _shop_by_name("丙火网络")
    rows = [
        _row(
            order_no="ROW_EMPTY_SHOP",
            payment_no="PAY_X",
            payment_detail=_alipay_detail("PAY_X", "10.00"),
            buyer_paid="10.00",
            status_zh="交易成功",
            paid_at="2026-04-29 23:00:00",
            shop_name="",
            shipped_at="2026-04-30 00:00:00",
            confirmed_at="2026-04-30 12:00:00",
            confirmed_amount="10.00",
        ),
    ]
    response = _post_import(client, shop.id, _build_xlsx(rows))
    assert response.status_code == 400


def test_import_400_when_file_empty(client):
    shop = _shop_by_name("丙火网络")
    response = client.post(
        f"/taobao/shops/{shop.id}/import",
        files={
            "file": (
                "empty.xlsx",
                b"",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# 新订单分流矩阵
# ---------------------------------------------------------------------------


def test_new_alipay_received_a_shop_to_store_alipay_wallet(client):
    """A 类店铺（丙火）alipay/received → store_alipay_wallet,扣 0.6% 手续费。"""
    shop = _shop_by_name("丙火网络")
    rows = [_row(
        order_no="ORDER_A1",
        payment_no="PAY_A1",
        payment_detail=_alipay_detail("PAY_A1", "100.00"),
        buyer_paid="100.00",
        status_zh="交易成功",
        paid_at="2026-04-29 23:57:43",
        shop_name="丙火网络",
        shipped_at="2026-04-30 00:03:21",
        confirmed_at="2026-04-30 14:00:00",
        confirmed_amount="100.00",
    )]
    response = _post_import(client, shop.id, _build_xlsx(rows))
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["createdOrders"] == 1

    # 100.00 → fee 0.60 → net 99.40
    assert _wallet_balance(shop.store_alipay_wallet_id) == Decimal("99.400000")
    assert _wallet_balance(shop.unconfirmed_alipay_wallet_id) == Decimal("0.000000")
    assert Decimal(payload["totalFeeAmount"]) == Decimal("0.60")


def test_new_alipay_received_b_shop_to_store_alipay_wallet(client):
    """B 类店铺（兔仔）alipay/received → store_alipay_wallet（兔仔电玩支付宝,type=TAOBAO）。"""
    shop = _shop_by_name("兔仔电玩")
    rows = [_row(
        order_no="ORDER_B1",
        payment_no="PAY_B1",
        payment_detail=_alipay_detail("PAY_B1", "50.00"),
        buyer_paid="50.00",
        status_zh="交易成功",
        paid_at="2026-04-29 23:57:43",
        shop_name="兔仔电玩",
        shipped_at="2026-04-30 00:03:21",
        confirmed_at="2026-04-30 14:00:00",
        confirmed_amount="50.00",
    )]
    response = _post_import(client, shop.id, _build_xlsx(rows))
    assert response.status_code == 200, response.text
    # 50 → fee 0.30 → net 49.70
    assert _wallet_balance(shop.store_alipay_wallet_id) == Decimal("49.700000")
    assert _wallet_balance(shop.bank_card_wallet_id) == Decimal("0.000000")


def test_new_wechat_received_to_aggregator_frozen_with_mature_at_from_confirmed_at(client):
    """wechat/received → aggregator_frozen，mature_at = confirmed_at + 7d。"""
    shop = _shop_by_name("丙火网络")
    confirmed_at_str = "2026-04-30 14:30:00"
    shipped_at_str = "2026-04-30 00:03:21"
    rows = [_row(
        order_no="ORDER_W1",
        payment_no="PAY_W1",
        payment_detail=_wechat_detail("PAY_W1", "200.00"),
        buyer_paid="200.00",
        status_zh="交易成功",
        paid_at="2026-04-29 23:57:43",
        shop_name="丙火网络",
        shipped_at=shipped_at_str,
        confirmed_at=confirmed_at_str,
        confirmed_amount="200.00",
    )]
    response = _post_import(client, shop.id, _build_xlsx(rows))
    assert response.status_code == 200, response.text

    # 200 → fee 1.20 → net 198.80
    assert _wallet_balance(shop.aggregator_frozen_wallet_id) == Decimal("198.800000")
    tx = _last_tx(shop.aggregator_frozen_wallet_id)
    assert tx is not None
    assert tx.mature_at is not None
    # mature_at 精确到分秒：与千牛后台一致 confirmed_at + 7 天
    confirmed_dt = datetime.strptime(confirmed_at_str, "%Y-%m-%d %H:%M:%S")
    expected_mature = confirmed_dt + timedelta(days=7)
    assert tx.mature_at.replace(tzinfo=None) == expected_mature


def test_mature_at_falls_back_to_shipped_at_when_confirmed_at_missing(client):
    """confirmed_at 缺失时,mature_at 兜底用 shipped_at + 7d。"""
    shop = _shop_by_name("丙火网络")
    shipped_at_str = "2026-04-30 00:03:21"
    rows = [_row(
        order_no="ORDER_FB",
        payment_no="PAY_FB",
        payment_detail=_wechat_detail("PAY_FB", "100.00"),
        buyer_paid="100.00",
        status_zh="交易成功",
        paid_at="2026-04-29 23:57:43",
        shop_name="丙火网络",
        shipped_at=shipped_at_str,
        confirmed_at="",  # 缺失
        confirmed_amount="100.00",
    )]
    response = _post_import(client, shop.id, _build_xlsx(rows))
    assert response.status_code == 200, response.text

    tx = _last_tx(shop.aggregator_frozen_wallet_id)
    # mature_at 精确到分秒：与千牛后台一致 shipped_at + 7 天
    shipped_dt = datetime.strptime(shipped_at_str, "%Y-%m-%d %H:%M:%S")
    expected = shipped_dt + timedelta(days=7)
    assert tx.mature_at.replace(tzinfo=None) == expected


def test_new_wechat_received_b_shop_also_to_aggregator_frozen(client):
    """B 类（兔仔）的 wechat/received 仍然走聚合冻结。"""
    shop = _shop_by_name("兔仔电玩")
    rows = [_row(
        order_no="ORDER_B_W1",
        payment_no="PAY_B_W1",
        payment_detail=_wechat_detail("PAY_B_W1", "60.00"),
        buyer_paid="60.00",
        status_zh="交易成功",
        paid_at="2026-04-29 23:57:43",
        shop_name="兔仔电玩",
        shipped_at="2026-04-30 00:03:21",
        confirmed_at="2026-04-30 14:00:00",
        confirmed_amount="60.00",
    )]
    response = _post_import(client, shop.id, _build_xlsx(rows))
    assert response.status_code == 200, response.text
    # 60 → fee 0.36 → net 59.64
    assert _wallet_balance(shop.aggregator_frozen_wallet_id) == Decimal("59.640000")


def test_new_alipay_shipped_unconfirmed_to_unconfirmed_alipay(client):
    """alipay/shipped_unconfirmed → unconfirmed_alipay,金额用买家实付（gross）,不扣手续费。"""
    shop = _shop_by_name("丙火网络")
    rows = [_row(
        order_no="ORDER_S1",
        payment_no="PAY_S1",
        payment_detail=_alipay_detail("PAY_S1", "27.50"),
        buyer_paid="27.50",
        status_zh="卖家已发货，等待买家确认",
        paid_at="2026-04-29 23:46:25",
        shop_name="丙火网络",
        shipped_at="2026-04-30 00:10:45",
        confirmed_at="",
        confirmed_amount="0.00",
    )]
    response = _post_import(client, shop.id, _build_xlsx(rows))
    assert response.status_code == 200, response.text
    # 在途：amount = gross = 27.50（不扣费）
    assert _wallet_balance(shop.unconfirmed_alipay_wallet_id) == Decimal("27.500000")
    assert _wallet_balance(shop.store_alipay_wallet_id) == Decimal("0.000000")

    # TaobaoOrder：amount=gross, fee_amount=NULL, confirmed_at=NULL
    order = _get_order("ORDER_S1")
    assert Decimal(order.amount) == Decimal("27.500000")
    assert Decimal(order.gross_amount) == Decimal("27.500000")
    assert order.fee_amount is None
    assert order.confirmed_at is None


def test_new_wechat_shipped_unconfirmed_to_unconfirmed_wechat(client):
    """wechat/shipped_unconfirmed → unconfirmed_wechat,不扣手续费。"""
    shop = _shop_by_name("丙火网络")
    rows = [_row(
        order_no="ORDER_S2",
        payment_no="PAY_S2",
        payment_detail=_wechat_detail("PAY_S2", "33.00"),
        buyer_paid="33.00",
        status_zh="卖家已发货，等待买家确认",
        paid_at="2026-04-29 23:46:25",
        shop_name="丙火网络",
        shipped_at="2026-04-30 00:10:45",
        confirmed_at="",
        confirmed_amount="0.00",
    )]
    response = _post_import(client, shop.id, _build_xlsx(rows))
    assert response.status_code == 200
    assert _wallet_balance(shop.unconfirmed_wechat_wallet_id) == Decimal("33.000000")


# ---------------------------------------------------------------------------
# 0.6% 手续费精度（CEO 边界值）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "gross,expected_net,expected_fee",
    [
        ("56.00", "55.660000", "0.340000"),    # 56*0.006=0.336 → 0.34
        ("269.00", "267.390000", "1.610000"),  # 269*0.006=1.614 → 1.61
        ("27.50", "27.330000", "0.170000"),    # 27.5*0.006=0.165 → ROUND_HALF_UP → 0.17
        ("100.00", "99.400000", "0.600000"),   # 100*0.006=0.60
        ("57.00", "56.660000", "0.340000"),    # 57*0.006=0.342 → 0.34
    ],
)
def test_fee_precision_rounding_half_up(client, gross, expected_net, expected_fee):
    """逐个边界金额跑 alipay/received，验证 net & fee 精度。"""
    shop = _shop_by_name("丙火网络")
    rows = [_row(
        order_no=f"FEE_{gross}",
        payment_no=f"PF_{gross}",
        payment_detail=_alipay_detail(f"PF_{gross}", gross),
        buyer_paid=gross,
        status_zh="交易成功",
        paid_at="2026-04-29 23:00:00",
        shop_name="丙火网络",
        shipped_at="2026-04-30 00:00:00",
        confirmed_at="2026-04-30 14:00:00",
        confirmed_amount=gross,
    )]
    response = _post_import(client, shop.id, _build_xlsx(rows))
    assert response.status_code == 200, response.text

    assert _wallet_balance(shop.store_alipay_wallet_id) == Decimal(expected_net)

    order = _get_order(f"FEE_{gross}")
    assert Decimal(order.amount) == Decimal(expected_net)
    assert Decimal(order.gross_amount) == Decimal(gross + "0000")  # numeric(18,6)
    assert Decimal(order.fee_amount) == Decimal(expected_fee)


def test_total_fee_amount_summed_across_received_rows(client):
    """totalFeeAmount = 所有 received 行 fee 之和。"""
    shop = _shop_by_name("丙火网络")
    rows = [
        _row(
            order_no=f"SUM_F_{i}",
            payment_no=f"P_SUM_{i}",
            payment_detail=_alipay_detail(f"P_SUM_{i}", str(amt)),
            buyer_paid=str(amt),
            status_zh="交易成功",
            paid_at="2026-04-29 23:00:00",
            shop_name="丙火网络",
            shipped_at="2026-04-30 00:00:00",
            confirmed_at="2026-04-30 14:00:00",
            confirmed_amount=str(amt),
        )
        for i, amt in enumerate(["56.00", "269.00", "100.00"])
    ]
    response = _post_import(client, shop.id, _build_xlsx(rows))
    assert response.status_code == 200, response.text
    payload = response.json()
    # 0.34 + 1.61 + 0.60 = 2.55
    assert Decimal(payload["totalFeeAmount"]) == Decimal("2.55")


# ---------------------------------------------------------------------------
# 跳过的状态
# ---------------------------------------------------------------------------


def test_skip_pending_pay_and_paid_unshipped(client):
    """等待买家付款 / 买家已付款等待发货 → 跳过，不入账。"""
    shop = _shop_by_name("丙火网络")
    rows = [
        _row(
            order_no="ORDER_PEND",
            payment_no="PAY_PEND",
            payment_detail=_alipay_detail("PAY_PEND", "0.00"),
            buyer_paid="0.00",
            status_zh="等待买家付款",
            paid_at="",
            shop_name="丙火网络",
            shipped_at="",
            confirmed_amount="0.00",
        ),
        _row(
            order_no="ORDER_UNSHIP",
            payment_no="PAY_UNSHIP",
            payment_detail=_alipay_detail("PAY_UNSHIP", "10.00"),
            buyer_paid="10.00",
            status_zh="买家已付款,等待卖家发货",
            paid_at="2026-04-29 23:00:00",
            shop_name="丙火网络",
            shipped_at="",
            confirmed_amount="0.00",
        ),
    ]
    response = _post_import(client, shop.id, _build_xlsx(rows))
    assert response.status_code == 200
    payload = response.json()
    assert payload["skippedUnpaidOrUnshipped"] == 2
    assert payload["createdOrders"] == 0
    assert _wallet_balance(shop.unconfirmed_alipay_wallet_id) == Decimal("0.000000")
    assert _wallet_balance(shop.store_alipay_wallet_id) == Decimal("0.000000")

    db = database.SessionLocal()
    try:
        orders = db.scalars(select(TaobaoOrder)).all()
        assert orders == []
    finally:
        db.close()


def test_skip_unknown_payment_method(client):
    """支付详情含怪字符串 → skippedUnknownPayment + 不入账。"""
    shop = _shop_by_name("丙火网络")
    rows = [_row(
        order_no="ORDER_UNKNOWN",
        payment_no="PAY_UNKNOWN",
        payment_detail="支付方式：未知通道，金额：50.00；",
        buyer_paid="50.00",
        status_zh="交易成功",
        paid_at="2026-04-29 23:00:00",
        shop_name="丙火网络",
        shipped_at="2026-04-30 00:00:00",
        confirmed_at="2026-04-30 14:00:00",
        confirmed_amount="50.00",
    )]
    response = _post_import(client, shop.id, _build_xlsx(rows))
    assert response.status_code == 200
    payload = response.json()
    assert payload["skippedUnknownPayment"] == 1
    assert payload["createdOrders"] == 0


def test_new_closed_order_no_credit(client):
    """新订单状态就是 closed → 不入账。"""
    shop = _shop_by_name("丙火网络")
    rows = [_row(
        order_no="ORDER_CLOSED",
        payment_no="PAY_CLOSED",
        payment_detail=_alipay_detail("PAY_CLOSED", "0.00"),
        buyer_paid="0.00",
        status_zh="交易关闭",
        paid_at="",
        shop_name="丙火网络",
        shipped_at="",
        confirmed_amount="0.00",
    )]
    response = _post_import(client, shop.id, _build_xlsx(rows))
    assert response.status_code == 200
    payload = response.json()
    assert payload["createdOrders"] == 1
    assert _wallet_balance(shop.store_alipay_wallet_id) == Decimal("0.000000")
    assert _wallet_balance(shop.unconfirmed_alipay_wallet_id) == Decimal("0.000000")

    order = _get_order("ORDER_CLOSED")
    assert order is not None
    assert order.status == TaobaoOrderStatus.CLOSED.value
    assert order.bookkeeping_wallet_id is None
    assert order.bookkeeping_tx_id is None


# ---------------------------------------------------------------------------
# Reconcile：状态变化
# ---------------------------------------------------------------------------


def test_reconcile_shipped_unconfirmed_to_received_alipay(client):
    """alipay 在途 → 确认：撤老钱包(unconfirmed_alipay 100) + 入新钱包(store_alipay 99.40)。

    差额 0.6 = fee 自然消失。
    """
    shop = _shop_by_name("丙火网络")
    # 1) 在途 100
    rows1 = [_row(
        order_no="ORDER_RECONCILE",
        payment_no="PAY_R1",
        payment_detail=_alipay_detail("PAY_R1", "100.00"),
        buyer_paid="100.00",
        status_zh="卖家已发货，等待买家确认",
        paid_at="2026-04-29 23:00:00",
        shop_name="丙火网络",
        shipped_at="2026-04-30 00:00:00",
        confirmed_amount="0.00",
    )]
    response = _post_import(client, shop.id, _build_xlsx(rows1))
    assert response.status_code == 200
    assert _wallet_balance(shop.unconfirmed_alipay_wallet_id) == Decimal("100.000000")
    assert _wallet_balance(shop.store_alipay_wallet_id) == Decimal("0.000000")

    # 2) 同一订单变 received（gross 100）
    rows2 = [_row(
        order_no="ORDER_RECONCILE",
        payment_no="PAY_R1",
        payment_detail=_alipay_detail("PAY_R1", "100.00"),
        buyer_paid="100.00",
        status_zh="交易成功",
        paid_at="2026-04-29 23:00:00",
        shop_name="丙火网络",
        shipped_at="2026-04-30 00:00:00",
        confirmed_at="2026-04-30 14:00:00",
        confirmed_amount="100.00",
    )]
    response = _post_import(client, shop.id, _build_xlsx(rows2))
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["statusChangedOrders"] == 1
    assert payload["createdOrders"] == 0

    # 老钱包：debit 100 → 0
    assert _wallet_balance(shop.unconfirmed_alipay_wallet_id) == Decimal("0.000000")
    # 新钱包：credit net=99.40
    assert _wallet_balance(shop.store_alipay_wallet_id) == Decimal("99.400000")
    # totalFee = 0.60
    assert Decimal(payload["totalFeeAmount"]) == Decimal("0.60")

    # 老钱包应该有 1 in + 1 out = 2 笔
    assert _wallet_tx_count(shop.unconfirmed_alipay_wallet_id) == 2
    last = _last_tx(shop.unconfirmed_alipay_wallet_id)
    direction = last.direction.value if hasattr(last.direction, "value") else last.direction
    assert direction == TransactionDirection.OUT.value
    assert "reconcile" in (last.remark or "")
    # debit 金额 = 老 amount = 100（gross,不是 net）
    assert Decimal(last.amount) == Decimal("100.000000")

    # TaobaoOrder：amount→net, gross/fee/confirmed_at 都补上
    order = _get_order("ORDER_RECONCILE")
    status_value = order.status.value if hasattr(order.status, "value") else order.status
    assert status_value == TaobaoOrderStatus.RECEIVED.value
    assert order.bookkeeping_wallet_id == shop.store_alipay_wallet_id
    assert Decimal(order.amount) == Decimal("99.400000")
    assert Decimal(order.gross_amount) == Decimal("100.000000")
    assert Decimal(order.fee_amount) == Decimal("0.600000")
    assert order.confirmed_at is not None


def test_reconcile_to_closed_no_new_credit(client):
    """状态从 shipped_unconfirmed → closed：撤老钱包,无新流水。"""
    shop = _shop_by_name("丙火网络")
    rows1 = [_row(
        order_no="ORDER_TO_CLOSED",
        payment_no="PAY_C1",
        payment_detail=_alipay_detail("PAY_C1", "80.00"),
        buyer_paid="80.00",
        status_zh="卖家已发货，等待买家确认",
        paid_at="2026-04-29 23:00:00",
        shop_name="丙火网络",
        shipped_at="2026-04-30 00:00:00",
        confirmed_amount="0.00",
    )]
    _post_import(client, shop.id, _build_xlsx(rows1))
    assert _wallet_balance(shop.unconfirmed_alipay_wallet_id) == Decimal("80.000000")

    rows2 = [_row(
        order_no="ORDER_TO_CLOSED",
        payment_no="PAY_C1",
        payment_detail=_alipay_detail("PAY_C1", "80.00"),
        buyer_paid="80.00",
        status_zh="交易关闭",
        paid_at="2026-04-29 23:00:00",
        shop_name="丙火网络",
        shipped_at="2026-04-30 00:00:00",
        confirmed_amount="0.00",
    )]
    response = _post_import(client, shop.id, _build_xlsx(rows2))
    assert response.status_code == 200
    payload = response.json()
    assert payload["closedReverted"] == 1

    assert _wallet_balance(shop.unconfirmed_alipay_wallet_id) == Decimal("0.000000")
    assert _wallet_balance(shop.store_alipay_wallet_id) == Decimal("0.000000")

    order = _get_order("ORDER_TO_CLOSED")
    assert order.status == TaobaoOrderStatus.CLOSED.value
    assert order.bookkeeping_wallet_id is None
    assert order.bookkeeping_tx_id is None


def test_reconcile_no_change_skipped(client):
    """状态没变 → skippedNoChange + 0 流水变化。"""
    shop = _shop_by_name("丙火网络")
    rows = [_row(
        order_no="ORDER_SAME",
        payment_no="PAY_SAME",
        payment_detail=_alipay_detail("PAY_SAME", "55.00"),
        buyer_paid="55.00",
        status_zh="卖家已发货，等待买家确认",
        paid_at="2026-04-29 23:00:00",
        shop_name="丙火网络",
        shipped_at="2026-04-30 00:00:00",
        confirmed_amount="0.00",
    )]
    _post_import(client, shop.id, _build_xlsx(rows))
    before_tx = _wallet_tx_count(shop.unconfirmed_alipay_wallet_id)

    response = _post_import(client, shop.id, _build_xlsx(rows))
    assert response.status_code == 200
    payload = response.json()
    assert payload["skippedNoChange"] == 1
    assert payload["statusChangedOrders"] == 0

    after_tx = _wallet_tx_count(shop.unconfirmed_alipay_wallet_id)
    assert before_tx == after_tx == 1


def test_reconcile_skip_jump_unconfirmed_to_received_wechat(client):
    """跳级 wechat：在途 120 → 确认 120 → debit 120 + credit net=119.28（fee 0.72）+ mature_at。"""
    shop = _shop_by_name("丙火网络")
    rows1 = [_row(
        order_no="ORDER_JUMP",
        payment_no="PAY_J1",
        payment_detail=_wechat_detail("PAY_J1", "120.00"),
        buyer_paid="120.00",
        status_zh="卖家已发货，等待买家确认",
        paid_at="2026-04-29 23:00:00",
        shop_name="丙火网络",
        shipped_at="2026-04-30 00:00:00",
        confirmed_amount="0.00",
    )]
    _post_import(client, shop.id, _build_xlsx(rows1))
    assert _wallet_balance(shop.unconfirmed_wechat_wallet_id) == Decimal("120.000000")

    rows2 = [_row(
        order_no="ORDER_JUMP",
        payment_no="PAY_J1",
        payment_detail=_wechat_detail("PAY_J1", "120.00"),
        buyer_paid="120.00",
        status_zh="交易成功",
        paid_at="2026-04-29 23:00:00",
        shop_name="丙火网络",
        shipped_at="2026-04-30 00:00:00",
        confirmed_at="2026-04-30 14:00:00",
        confirmed_amount="120.00",
    )]
    response = _post_import(client, shop.id, _build_xlsx(rows2))
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["statusChangedOrders"] == 1

    assert _wallet_balance(shop.unconfirmed_wechat_wallet_id) == Decimal("0.000000")
    # 120 → fee 0.72 → net 119.28
    assert _wallet_balance(shop.aggregator_frozen_wallet_id) == Decimal("119.280000")

    new_tx = _last_tx(shop.aggregator_frozen_wallet_id)
    assert new_tx.mature_at is not None


# ---------------------------------------------------------------------------
# 自动解冻（ImportReport 末尾自动跑）
# ---------------------------------------------------------------------------


def _seed_aggregator_frozen_tx(
    shop: TaobaoShop,
    amount: Decimal,
    mature_at: datetime,
    *,
    bind_to_order: bool = True,
    order_number: str | None = None,
) -> int:
    """灌一笔聚合冻结流水（可绑订单）。"""
    db = database.SessionLocal()
    try:
        tx = credit(
            db,
            shop.aggregator_frozen_wallet_id,
            amount,
            remark="测试种子",
            mature_at=mature_at,
        )
        if bind_to_order:
            order = TaobaoOrder(
                shop_id=shop.id,
                order_number=order_number or f"SEED_{tx.id}",
                payment_method=TaobaoOrderPaymentMethod.WECHAT.value,
                amount=amount,
                gross_amount=amount,
                status=TaobaoOrderStatus.RECEIVED.value,
                bookkeeping_wallet_id=shop.aggregator_frozen_wallet_id,
                bookkeeping_tx_id=tx.id,
            )
            db.add(order)
        db.commit()
        return tx.id
    finally:
        db.close()


def test_auto_release_on_import_moves_matured_to_available(client):
    """fixture 灌入到期流水 → 导入新订单 → 报告含 autoReleased*。"""
    shop = _shop_by_name("丙火网络")
    now = datetime.now(timezone.utc)
    _seed_aggregator_frozen_tx(shop, Decimal("100"), now - timedelta(days=1), order_number="MAT_AR_1")
    _seed_aggregator_frozen_tx(shop, Decimal("50"), now - timedelta(hours=2), order_number="MAT_AR_2")
    _seed_aggregator_frozen_tx(shop, Decimal("80"), now + timedelta(days=3), order_number="FUT_AR")

    # 解冻前 frozen=230, available=0
    assert _wallet_balance(shop.aggregator_frozen_wallet_id) == Decimal("230.000000")
    assert _wallet_balance(shop.aggregator_available_wallet_id) == Decimal("0.000000")

    # 导入空数据行（仅触发末尾自动解冻）
    rows: list[list] = []
    response = _post_import(client, shop.id, _build_xlsx(rows))
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["autoReleasedCount"] == 2
    assert Decimal(payload["autoReleasedAmount"]) == Decimal("150")

    # 余额：frozen 80（仅未到期）, available 150
    assert _wallet_balance(shop.aggregator_frozen_wallet_id) == Decimal("80.000000")
    assert _wallet_balance(shop.aggregator_available_wallet_id) == Decimal("150.000000")


def test_auto_release_no_matured_returns_zero(client):
    """无任何到期流水时 autoReleased*=0,不动余额。"""
    shop = _shop_by_name("丙火网络")
    now = datetime.now(timezone.utc)
    _seed_aggregator_frozen_tx(shop, Decimal("99"), now + timedelta(days=2), order_number="FUT_ONLY_AR")

    response = _post_import(client, shop.id, _build_xlsx([]))
    assert response.status_code == 200
    payload = response.json()
    assert payload["autoReleasedCount"] == 0
    assert Decimal(payload["autoReleasedAmount"]) == Decimal("0")

    assert _wallet_balance(shop.aggregator_frozen_wallet_id) == Decimal("99.000000")
    assert _wallet_balance(shop.aggregator_available_wallet_id) == Decimal("0.000000")


def test_release_endpoint_removed_returns_404_or_405(client):
    """一键解冻端点已删,POST 应 404/405。"""
    shop = _shop_by_name("丙火网络")
    response = client.post(f"/taobao/shops/{shop.id}/aggregator/release")
    assert response.status_code in (404, 405), response.text


# ---------------------------------------------------------------------------
# 综合：报告字段
# ---------------------------------------------------------------------------


def test_full_report_counts(client):
    """5 行综合：报告字段全到位。"""
    shop = _shop_by_name("丙火网络")
    rows = [
        # 1) received alipay 10 → fee 0.06 → net 9.94
        _row(
            order_no="F_RECV_AL",
            payment_no="P1",
            payment_detail=_alipay_detail("P1", "10.00"),
            buyer_paid="10.00",
            status_zh="交易成功",
            paid_at="2026-04-29 23:00:00",
            shop_name="丙火网络",
            shipped_at="2026-04-30 00:00:00",
            confirmed_at="2026-04-30 14:00:00",
            confirmed_amount="10.00",
        ),
        # 2) shipped wechat 20 (无 fee)
        _row(
            order_no="F_SHIP_WX",
            payment_no="P2",
            payment_detail=_wechat_detail("P2", "20.00"),
            buyer_paid="20.00",
            status_zh="卖家已发货，等待买家确认",
            paid_at="2026-04-29 23:00:00",
            shop_name="丙火网络",
            shipped_at="2026-04-30 00:00:00",
            confirmed_amount="0.00",
        ),
        # 3) skip pending pay
        _row(
            order_no="F_PEND",
            payment_no="P3",
            payment_detail=_alipay_detail("P3", "0.00"),
            buyer_paid="0.00",
            status_zh="等待买家付款",
            paid_at="",
            shop_name="丙火网络",
            shipped_at="",
            confirmed_amount="0.00",
        ),
        # 4) skip unknown payment
        _row(
            order_no="F_UNKNOWN",
            payment_no="P4",
            payment_detail="支付方式：信用卡，金额：30.00；",
            buyer_paid="30.00",
            status_zh="交易成功",
            paid_at="2026-04-29 23:00:00",
            shop_name="丙火网络",
            shipped_at="2026-04-30 00:00:00",
            confirmed_at="2026-04-30 14:00:00",
            confirmed_amount="30.00",
        ),
        # 5) closed
        _row(
            order_no="F_CLOSED",
            payment_no="P5",
            payment_detail=_alipay_detail("P5", "0.00"),
            buyer_paid="0.00",
            status_zh="交易关闭",
            paid_at="",
            shop_name="丙火网络",
            shipped_at="",
            confirmed_amount="0.00",
        ),
    ]
    response = _post_import(client, shop.id, _build_xlsx(rows))
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["shopName"] == "丙火网络"
    assert payload["totalRowsParsed"] == 5
    assert payload["createdOrders"] == 3
    assert payload["statusChangedOrders"] == 0
    assert payload["closedReverted"] == 0
    assert payload["skippedNoChange"] == 0
    assert payload["skippedUnpaidOrUnshipped"] == 1
    assert payload["skippedUnknownPayment"] == 1
    assert payload["errors"] == []
    # 自动解冻 / 总手续费 字段都返回
    assert "autoReleasedAmount" in payload
    assert "autoReleasedCount" in payload
    assert "totalFeeAmount" in payload
    # 仅 1 个 received 行（10 → fee 0.06）
    assert Decimal(payload["totalFeeAmount"]) == Decimal("0.06")


def test_atomic_transaction_no_partial_on_db_error(client, monkeypatch):
    """单一事务原子：一条流水抛错应整个 rollback。"""
    shop = _shop_by_name("丙火网络")
    rows = [
        _row(
            order_no="OK_1",
            payment_no="P1",
            payment_detail=_alipay_detail("P1", "10.00"),
            buyer_paid="10.00",
            status_zh="交易成功",
            paid_at="2026-04-29 23:00:00",
            shop_name="丙火网络",
            shipped_at="2026-04-30 00:00:00",
            confirmed_at="2026-04-30 14:00:00",
            confirmed_amount="10.00",
        ),
        _row(
            order_no="BAD_2",
            payment_no="P2",
            payment_detail=_alipay_detail("P2", "20.00"),
            buyer_paid="20.00",
            status_zh="交易成功",
            paid_at="2026-04-29 23:00:00",
            shop_name="丙火网络",
            shipped_at="2026-04-30 00:00:00",
            confirmed_at="2026-04-30 14:00:00",
            confirmed_amount="20.00",
        ),
    ]

    import src.services.taobao_import as ti_module

    original_credit = ti_module.credit
    call_counter = {"n": 0}

    def boom(*args, **kwargs):
        call_counter["n"] += 1
        if call_counter["n"] == 2:
            raise RuntimeError("simulated db failure")
        return original_credit(*args, **kwargs)

    monkeypatch.setattr(ti_module, "credit", boom)

    no_raise_client = TestClient(app, raise_server_exceptions=False)
    response = no_raise_client.post(
        f"/taobao/shops/{shop.id}/import",
        files={
            "file": (
                "x.xlsx",
                _build_xlsx(rows),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert response.status_code == 500

    assert _wallet_balance(shop.store_alipay_wallet_id) == Decimal("0.000000")

    db = database.SessionLocal()
    try:
        orders = db.scalars(select(TaobaoOrder)).all()
        assert orders == []
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 大样本回归（v2 14 列分布）
# ---------------------------------------------------------------------------


def test_large_sample_distribution_v2(client):
    """根据 scripts/qianniu_sample_v2.json 状态分布生成 1738 条（丙火），跑通 + 对账。

    v2 实际样例分布:
    - 交易成功(received)            : 947
    - 卖家已发货,等待买家确认(在途) : 676
    - 交易关闭                      : 96
    - 买家已付款,等待卖家发货(skip) : 19

    支付方式分布: wechat 1325 / alipay 413 (近似)
    """
    shop = _shop_by_name("丙火网络")
    rows: list[list] = []
    idx = 0

    def add(status: str, amount: Decimal, payment: str = "alipay"):
        nonlocal idx
        idx += 1
        order_no = f"BIG_{idx:04d}"
        detail_fn = _alipay_detail if payment == "alipay" else _wechat_detail
        confirm_amount = str(amount) if status == "交易成功" else "0.00"
        ship_time = (
            "2026-04-30 00:00:00"
            if status in ("交易成功", "卖家已发货，等待买家确认")
            else ""
        )
        confirm_time = (
            "2026-04-30 14:00:00" if status == "交易成功" else ""
        )
        pay_time = (
            "2026-04-29 23:00:00"
            if status in ("交易成功", "卖家已发货，等待买家确认", "买家已付款,等待卖家发货")
            else ""
        )
        rows.append(_row(
            order_no=order_no,
            payment_no=f"P{idx:04d}",
            payment_detail=detail_fn(f"P{idx:04d}", str(amount)),
            buyer_paid=str(amount),
            status_zh=status,
            paid_at=pay_time,
            shop_name="丙火网络",
            shipped_at=ship_time,
            confirmed_at=confirm_time,
            confirmed_amount=confirm_amount,
        ))

    # received 947
    for i in range(947):
        add("交易成功", Decimal("100.00"), "alipay" if i % 4 == 0 else "wechat")
    # shipped 676
    for i in range(676):
        add("卖家已发货，等待买家确认", Decimal("50.00"), "alipay" if i % 4 == 0 else "wechat")
    # closed 96
    for _ in range(96):
        add("交易关闭", Decimal("0.00"))
    # paid_unshipped 19
    for _ in range(19):
        add("买家已付款,等待卖家发货", Decimal("30.00"))

    assert len(rows) == 947 + 676 + 96 + 19  # 1738

    response = _post_import(client, shop.id, _build_xlsx(rows))
    assert response.status_code == 200, response.text
    p = response.json()

    assert p["totalRowsParsed"] == 1738
    assert p["createdOrders"] == 947 + 676 + 96
    assert p["skippedUnpaidOrUnshipped"] == 19
    assert p["skippedUnknownPayment"] == 0
    assert p["statusChangedOrders"] == 0
    assert p["closedReverted"] == 0
    assert p["errors"] == []
    # 947 个 received,每条 100 → fee 0.60 → 总 fee = 947 * 0.60 = 568.20
    assert Decimal(p["totalFeeAmount"]) == Decimal("568.20")
