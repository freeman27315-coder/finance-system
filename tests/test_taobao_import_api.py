"""千牛 Excel 导入 + 订单 reconcile + 状态变化金流 综合测试。

涵盖：
- 端点 happy path：新订单 / 老订单 / 状态变化 / 关闭 / 跳过
- 三维分流矩阵（A 类 vs B 类 / alipay vs wechat / shipped_unconfirmed vs received）
- 微信/received → aggregator_frozen + mature_at = received_at + 7d
- 状态变化 reconcile：撤老钱包流水 + 入新钱包
- 状态变成 closed：撤账无新流水
- 错误处理：404 shop / 400 非 .xlsx / 400 表头错
- 跳过未付款 / 未发货 / 未知支付方式
- 单一事务原子性
"""
from __future__ import annotations

from datetime import datetime, timedelta
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
)
from src.services.assets import ensure_default_asset_wallets
from src.services.taobao import ensure_default_taobao_wallets


HEADERS = [
    "订单编号",
    "支付单号",
    "支付详情",
    "买家实付金额",
    "订单状态",
    "订单付款时间",
    "店铺名称",
    "发货时间",
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


# ---------------------------------------------------------------------------
# 端点错误路径
# ---------------------------------------------------------------------------


def test_import_404_when_shop_not_found(client):
    content = _build_xlsx([])
    response = _post_import(client, 9999, content)
    assert response.status_code == 404
    assert "店铺" in response.json()["detail"]


def test_import_400_when_not_xlsx(client):
    shop = _shop_by_name("丙火电玩")
    response = client.post(
        f"/taobao/shops/{shop.id}/import",
        files={"file": ("export.csv", b"some,csv,data", "text/csv")},
    )
    assert response.status_code == 400
    assert ".xlsx" in response.json()["detail"]


def test_import_400_when_header_wrong(client):
    shop = _shop_by_name("丙火电玩")
    bad_headers = ["订单编号", "支付单号", "WRONG"] + HEADERS[3:]
    content = _build_xlsx([], headers=bad_headers)
    response = _post_import(client, shop.id, content)
    assert response.status_code == 400
    assert "表头" in response.json()["detail"]


def test_import_400_when_columns_too_few(client):
    shop = _shop_by_name("丙火电玩")
    content = _build_xlsx([], headers=HEADERS[:5])
    response = _post_import(client, shop.id, content)
    assert response.status_code == 400


def test_import_400_when_row_shop_name_mismatched(client):
    """行内店铺名 != 上传 shop.name → 400 + 错误信息含两个店铺名 + 整体回滚。"""
    shop = _shop_by_name("丙火电玩")
    rows = [
        [
            "ROW_OK",
            "PAY_OK",
            _alipay_detail("PAY_OK", "10.00"),
            "10.00",
            "交易成功",
            "2026-04-29 23:00:00",
            "丙火电玩",
            "2026-04-30 00:00:00",
            "10.00",
        ],
        [
            "ROW_BAD",
            "PAY_BAD",
            _alipay_detail("PAY_BAD", "20.00"),
            "20.00",
            "交易成功",
            "2026-04-29 23:00:00",
            "兔仔电玩",  # 不匹配上传的丙火电玩
            "2026-04-30 00:00:00",
            "20.00",
        ],
    ]
    response = _post_import(client, shop.id, _build_xlsx(rows))
    assert response.status_code == 400, response.text
    detail = response.json()["detail"]
    assert "兔仔电玩" in detail
    assert "丙火电玩" in detail

    # 整体回滚：第一行也不应入账
    assert _wallet_balance(shop.store_alipay_wallet_id) == Decimal("0.000000")

    db = database.SessionLocal()
    try:
        orders = db.scalars(select(TaobaoOrder)).all()
        assert orders == []
    finally:
        db.close()


def test_import_400_when_row_shop_name_empty(client):
    """行内店铺名为空 → 视为不匹配 → 400。"""
    shop = _shop_by_name("丙火电玩")
    rows = [
        [
            "ROW_EMPTY_SHOP",
            "PAY_X",
            _alipay_detail("PAY_X", "10.00"),
            "10.00",
            "交易成功",
            "2026-04-29 23:00:00",
            "",  # 空店铺名
            "2026-04-30 00:00:00",
            "10.00",
        ],
    ]
    response = _post_import(client, shop.id, _build_xlsx(rows))
    assert response.status_code == 400


def test_import_400_when_file_empty(client):
    shop = _shop_by_name("丙火电玩")
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
    """A 类店铺（丙火电玩）alipay/received → store_alipay_wallet（资产支付宝子钱包）。"""
    shop = _shop_by_name("丙火电玩")
    rows = [[
        "ORDER_A1",
        "PAY_A1",
        _alipay_detail("PAY_A1", "100.00"),
        "100.00",
        "交易成功",
        "2026-04-29 23:57:43",
        "丙火电玩",
        "2026-04-30 00:03:21",
        "100.00",
    ]]
    response = _post_import(client, shop.id, _build_xlsx(rows))
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["createdOrders"] == 1

    assert _wallet_balance(shop.store_alipay_wallet_id) == Decimal("100.000000")
    assert _wallet_balance(shop.unconfirmed_alipay_wallet_id) == Decimal("0.000000")


def test_new_alipay_received_b_shop_to_store_alipay_wallet(client):
    """B 类店铺（兔仔电玩）alipay/received → store_alipay_wallet（兔仔电玩支付宝,type=TAOBAO）,不再进 bank_card。"""
    shop = _shop_by_name("兔仔电玩")
    rows = [[
        "ORDER_B1",
        "PAY_B1",
        _alipay_detail("PAY_B1", "50.00"),
        "50.00",
        "交易成功",
        "2026-04-29 23:57:43",
        "兔仔电玩",
        "2026-04-30 00:03:21",
        "50.00",
    ]]
    response = _post_import(client, shop.id, _build_xlsx(rows))
    assert response.status_code == 200, response.text
    assert _wallet_balance(shop.store_alipay_wallet_id) == Decimal("50.000000")
    assert _wallet_balance(shop.bank_card_wallet_id) == Decimal("0.000000")


def test_new_wechat_received_to_aggregator_frozen_with_mature_at(client):
    """wechat/received → aggregator_frozen，且 mature_at = received_at + 7d。"""
    shop = _shop_by_name("丙火电玩")
    received_at_str = "2026-04-30 00:03:21"
    rows = [[
        "ORDER_W1",
        "PAY_W1",
        _wechat_detail("PAY_W1", "200.00"),
        "200.00",
        "交易成功",
        "2026-04-29 23:57:43",
        "丙火电玩",
        received_at_str,
        "200.00",
    ]]
    response = _post_import(client, shop.id, _build_xlsx(rows))
    assert response.status_code == 200, response.text

    assert _wallet_balance(shop.aggregator_frozen_wallet_id) == Decimal("200.000000")
    tx = _last_tx(shop.aggregator_frozen_wallet_id)
    assert tx is not None
    assert tx.mature_at is not None
    expected_mature = datetime.strptime(received_at_str, "%Y-%m-%d %H:%M:%S") + timedelta(days=7)
    assert tx.mature_at.replace(tzinfo=None) == expected_mature


def test_new_wechat_received_b_shop_also_to_aggregator_frozen(client):
    """B 类（兔仔）的 wechat/received 仍然走聚合冻结（聚合支付独立于店铺归属）。"""
    shop = _shop_by_name("兔仔电玩")
    rows = [[
        "ORDER_B_W1",
        "PAY_B_W1",
        _wechat_detail("PAY_B_W1", "60.00"),
        "60.00",
        "交易成功",
        "2026-04-29 23:57:43",
        "兔仔电玩",
        "2026-04-30 00:03:21",
        "60.00",
    ]]
    response = _post_import(client, shop.id, _build_xlsx(rows))
    assert response.status_code == 200, response.text
    assert _wallet_balance(shop.aggregator_frozen_wallet_id) == Decimal("60.000000")
    assert _wallet_balance(shop.bank_card_wallet_id) == Decimal("0.000000")


def test_new_alipay_shipped_unconfirmed_to_unconfirmed_alipay(client):
    """alipay/shipped_unconfirmed → unconfirmed_alipay,金额用买家实付。"""
    shop = _shop_by_name("丙火电玩")
    rows = [[
        "ORDER_S1",
        "PAY_S1",
        _alipay_detail("PAY_S1", "27.50"),
        "27.50",
        "卖家已发货，等待买家确认",
        "2026-04-29 23:46:25",
        "丙火电玩",
        "2026-04-30 00:10:45",
        "0.00",
    ]]
    response = _post_import(client, shop.id, _build_xlsx(rows))
    assert response.status_code == 200, response.text
    assert _wallet_balance(shop.unconfirmed_alipay_wallet_id) == Decimal("27.500000")
    assert _wallet_balance(shop.store_alipay_wallet_id) == Decimal("0.000000")


def test_new_wechat_shipped_unconfirmed_to_unconfirmed_wechat(client):
    """wechat/shipped_unconfirmed → unconfirmed_wechat。"""
    shop = _shop_by_name("丙火电玩")
    rows = [[
        "ORDER_S2",
        "PAY_S2",
        _wechat_detail("PAY_S2", "33.00"),
        "33.00",
        "卖家已发货，等待买家确认",
        "2026-04-29 23:46:25",
        "丙火电玩",
        "2026-04-30 00:10:45",
        "0.00",
    ]]
    response = _post_import(client, shop.id, _build_xlsx(rows))
    assert response.status_code == 200
    assert _wallet_balance(shop.unconfirmed_wechat_wallet_id) == Decimal("33.000000")


# ---------------------------------------------------------------------------
# 跳过的状态
# ---------------------------------------------------------------------------


def test_skip_pending_pay_and_paid_unshipped(client):
    """等待买家付款 / 买家已付款等待发货 → 跳过，不入账。"""
    shop = _shop_by_name("丙火电玩")
    rows = [
        [
            "ORDER_PEND",
            "PAY_PEND",
            _alipay_detail("PAY_PEND", "0.00"),
            "0.00",
            "等待买家付款",
            "",
            "丙火电玩",
            "",
            "0.00",
        ],
        [
            "ORDER_UNSHIP",
            "PAY_UNSHIP",
            _alipay_detail("PAY_UNSHIP", "10.00"),
            "10.00",
            "买家已付款,等待卖家发货",
            "2026-04-29 23:00:00",
            "丙火电玩",
            "",
            "0.00",
        ],
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
    """支付详情含怪字符串(无 微信支付/支付宝) → skippedUnknownPayment + 不入账 + 不建订单。"""
    shop = _shop_by_name("丙火电玩")
    rows = [[
        "ORDER_UNKNOWN",
        "PAY_UNKNOWN",
        "支付方式：未知通道，金额：50.00；",  # 没有"微信支付"也没有"支付宝"
        "50.00",
        "交易成功",
        "2026-04-29 23:00:00",
        "丙火电玩",
        "2026-04-30 00:00:00",
        "50.00",
    ]]
    response = _post_import(client, shop.id, _build_xlsx(rows))
    assert response.status_code == 200
    payload = response.json()
    assert payload["skippedUnknownPayment"] == 1
    assert payload["createdOrders"] == 0


def test_new_closed_order_no_credit(client):
    """新订单状态就是 closed → 不入账,但 TaobaoOrder 仍写一行（status=closed）。"""
    shop = _shop_by_name("丙火电玩")
    rows = [[
        "ORDER_CLOSED",
        "PAY_CLOSED",
        _alipay_detail("PAY_CLOSED", "0.00"),
        "0.00",
        "交易关闭",
        "",
        "丙火电玩",
        "",
        "0.00",
    ]]
    response = _post_import(client, shop.id, _build_xlsx(rows))
    assert response.status_code == 200
    payload = response.json()
    assert payload["createdOrders"] == 1
    assert _wallet_balance(shop.store_alipay_wallet_id) == Decimal("0.000000")
    assert _wallet_balance(shop.unconfirmed_alipay_wallet_id) == Decimal("0.000000")

    db = database.SessionLocal()
    try:
        order = db.scalar(select(TaobaoOrder).where(TaobaoOrder.order_number == "ORDER_CLOSED"))
        assert order is not None
        assert order.status == TaobaoOrderStatus.CLOSED.value
        assert order.bookkeeping_wallet_id is None
        assert order.bookkeeping_tx_id is None
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Reconcile：状态变化
# ---------------------------------------------------------------------------


def test_reconcile_shipped_unconfirmed_to_received(client):
    """状态从 shipped_unconfirmed → received：撤老钱包(unconfirmed_alipay) + 入新钱包(store_alipay_wallet)。"""
    shop = _shop_by_name("丙火电玩")
    # 第一次导入：shipped_unconfirmed
    rows1 = [[
        "ORDER_RECONCILE",
        "PAY_R1",
        _alipay_detail("PAY_R1", "100.00"),
        "100.00",
        "卖家已发货，等待买家确认",
        "2026-04-29 23:00:00",
        "丙火电玩",
        "2026-04-30 00:00:00",
        "0.00",
    ]]
    response = _post_import(client, shop.id, _build_xlsx(rows1))
    assert response.status_code == 200
    assert _wallet_balance(shop.unconfirmed_alipay_wallet_id) == Decimal("100.000000")
    assert _wallet_balance(shop.store_alipay_wallet_id) == Decimal("0.000000")

    # 第二次导入：同一订单变成 received
    rows2 = [[
        "ORDER_RECONCILE",
        "PAY_R1",
        _alipay_detail("PAY_R1", "100.00"),
        "100.00",
        "交易成功",
        "2026-04-29 23:00:00",
        "丙火电玩",
        "2026-04-30 00:00:00",
        "100.00",
    ]]
    response = _post_import(client, shop.id, _build_xlsx(rows2))
    assert response.status_code == 200
    payload = response.json()
    assert payload["statusChangedOrders"] == 1
    assert payload["createdOrders"] == 0

    # 老钱包（unconfirmed_alipay）应该被 debit 100,余额回 0
    assert _wallet_balance(shop.unconfirmed_alipay_wallet_id) == Decimal("0.000000")
    # 新钱包（store_alipay_wallet）应该 +100
    assert _wallet_balance(shop.store_alipay_wallet_id) == Decimal("100.000000")

    # 老钱包应该有 1 in + 1 out = 2 笔流水
    assert _wallet_tx_count(shop.unconfirmed_alipay_wallet_id) == 2

    # 老钱包最近一笔应该是 OUT 方向
    last = _last_tx(shop.unconfirmed_alipay_wallet_id)
    direction = last.direction.value if hasattr(last.direction, "value") else last.direction
    assert direction == TransactionDirection.OUT.value
    assert "reconcile" in (last.remark or "")

    # TaobaoOrder 状态应该更新
    db = database.SessionLocal()
    try:
        order = db.scalar(
            select(TaobaoOrder).where(TaobaoOrder.order_number == "ORDER_RECONCILE")
        )
        status_value = order.status.value if hasattr(order.status, "value") else order.status
        assert status_value == TaobaoOrderStatus.RECEIVED.value
        assert order.bookkeeping_wallet_id == shop.store_alipay_wallet_id
    finally:
        db.close()


def test_reconcile_to_closed_no_new_credit(client):
    """状态从 shipped_unconfirmed → closed：撤老钱包,无新流水。"""
    shop = _shop_by_name("丙火电玩")
    rows1 = [[
        "ORDER_TO_CLOSED",
        "PAY_C1",
        _alipay_detail("PAY_C1", "80.00"),
        "80.00",
        "卖家已发货，等待买家确认",
        "2026-04-29 23:00:00",
        "丙火电玩",
        "2026-04-30 00:00:00",
        "0.00",
    ]]
    _post_import(client, shop.id, _build_xlsx(rows1))
    assert _wallet_balance(shop.unconfirmed_alipay_wallet_id) == Decimal("80.000000")

    rows2 = [[
        "ORDER_TO_CLOSED",
        "PAY_C1",
        _alipay_detail("PAY_C1", "80.00"),
        "80.00",
        "交易关闭",
        "2026-04-29 23:00:00",
        "丙火电玩",
        "2026-04-30 00:00:00",
        "0.00",
    ]]
    response = _post_import(client, shop.id, _build_xlsx(rows2))
    assert response.status_code == 200
    payload = response.json()
    assert payload["closedReverted"] == 1

    assert _wallet_balance(shop.unconfirmed_alipay_wallet_id) == Decimal("0.000000")
    assert _wallet_balance(shop.store_alipay_wallet_id) == Decimal("0.000000")

    db = database.SessionLocal()
    try:
        order = db.scalar(
            select(TaobaoOrder).where(TaobaoOrder.order_number == "ORDER_TO_CLOSED")
        )
        assert order.status == TaobaoOrderStatus.CLOSED.value
        assert order.bookkeeping_wallet_id is None
        assert order.bookkeeping_tx_id is None
    finally:
        db.close()


def test_reconcile_no_change_skipped(client):
    """状态没变 → skippedNoChange + 0 流水变化。"""
    shop = _shop_by_name("丙火电玩")
    rows = [[
        "ORDER_SAME",
        "PAY_SAME",
        _alipay_detail("PAY_SAME", "55.00"),
        "55.00",
        "卖家已发货，等待买家确认",
        "2026-04-29 23:00:00",
        "丙火电玩",
        "2026-04-30 00:00:00",
        "0.00",
    ]]
    _post_import(client, shop.id, _build_xlsx(rows))
    before_tx = _wallet_tx_count(shop.unconfirmed_alipay_wallet_id)

    response = _post_import(client, shop.id, _build_xlsx(rows))
    assert response.status_code == 200
    payload = response.json()
    assert payload["skippedNoChange"] == 1
    assert payload["statusChangedOrders"] == 0

    after_tx = _wallet_tx_count(shop.unconfirmed_alipay_wallet_id)
    assert before_tx == after_tx == 1


def test_reconcile_skip_jump_unconfirmed_to_received(client):
    """跳级：第一次 shipped_unconfirmed，下一次直接 received（情况 5），同情况 3 处理。"""
    shop = _shop_by_name("丙火电玩")
    rows1 = [[
        "ORDER_JUMP",
        "PAY_J1",
        _wechat_detail("PAY_J1", "120.00"),
        "120.00",
        "卖家已发货，等待买家确认",
        "2026-04-29 23:00:00",
        "丙火电玩",
        "2026-04-30 00:00:00",
        "0.00",
    ]]
    _post_import(client, shop.id, _build_xlsx(rows1))
    assert _wallet_balance(shop.unconfirmed_wechat_wallet_id) == Decimal("120.000000")

    # 跳到 received（wechat/received → aggregator_frozen + mature_at）
    rows2 = [[
        "ORDER_JUMP",
        "PAY_J1",
        _wechat_detail("PAY_J1", "120.00"),
        "120.00",
        "交易成功",
        "2026-04-29 23:00:00",
        "丙火电玩",
        "2026-04-30 00:00:00",
        "120.00",
    ]]
    response = _post_import(client, shop.id, _build_xlsx(rows2))
    assert response.status_code == 200
    payload = response.json()
    assert payload["statusChangedOrders"] == 1

    assert _wallet_balance(shop.unconfirmed_wechat_wallet_id) == Decimal("0.000000")
    assert _wallet_balance(shop.aggregator_frozen_wallet_id) == Decimal("120.000000")

    new_tx = _last_tx(shop.aggregator_frozen_wallet_id)
    assert new_tx.mature_at is not None


# ---------------------------------------------------------------------------
# 综合：多行 + 报告字段
# ---------------------------------------------------------------------------


def test_full_report_counts(client):
    shop = _shop_by_name("丙火电玩")
    rows = [
        # 1) 新订单 received alipay
        [
            "F_RECV_AL",
            "P1",
            _alipay_detail("P1", "10.00"),
            "10.00",
            "交易成功",
            "2026-04-29 23:00:00",
            "丙火电玩",
            "2026-04-30 00:00:00",
            "10.00",
        ],
        # 2) 新订单 shipped_unconfirmed wechat
        [
            "F_SHIP_WX",
            "P2",
            _wechat_detail("P2", "20.00"),
            "20.00",
            "卖家已发货，等待买家确认",
            "2026-04-29 23:00:00",
            "丙火电玩",
            "2026-04-30 00:00:00",
            "0.00",
        ],
        # 3) 跳过: 等待付款
        [
            "F_PEND",
            "P3",
            _alipay_detail("P3", "0.00"),
            "0.00",
            "等待买家付款",
            "",
            "丙火电玩",
            "",
            "0.00",
        ],
        # 4) 跳过: 未知支付
        [
            "F_UNKNOWN",
            "P4",
            "支付方式：信用卡，金额：30.00；",
            "30.00",
            "交易成功",
            "2026-04-29 23:00:00",
            "丙火电玩",
            "2026-04-30 00:00:00",
            "30.00",
        ],
        # 5) closed 新单
        [
            "F_CLOSED",
            "P5",
            _alipay_detail("P5", "0.00"),
            "0.00",
            "交易关闭",
            "",
            "丙火电玩",
            "",
            "0.00",
        ],
    ]
    response = _post_import(client, shop.id, _build_xlsx(rows))
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["shopName"] == "丙火电玩"
    assert payload["totalRowsParsed"] == 5
    assert payload["createdOrders"] == 3  # received + shipped + closed-new
    assert payload["statusChangedOrders"] == 0
    assert payload["closedReverted"] == 0
    assert payload["skippedNoChange"] == 0
    assert payload["skippedUnpaidOrUnshipped"] == 1
    assert payload["skippedUnknownPayment"] == 1
    assert payload["errors"] == []


def test_atomic_transaction_no_partial_on_db_error(client, monkeypatch):
    """单一事务原子：一条流水抛错应整个 rollback。"""
    shop = _shop_by_name("丙火电玩")
    rows = [
        [
            "OK_1",
            "P1",
            _alipay_detail("P1", "10.00"),
            "10.00",
            "交易成功",
            "2026-04-29 23:00:00",
            "丙火电玩",
            "2026-04-30 00:00:00",
            "10.00",
        ],
        [
            "BAD_2",
            "P2",
            _alipay_detail("P2", "20.00"),
            "20.00",
            "交易成功",
            "2026-04-29 23:00:00",
            "丙火电玩",
            "2026-04-30 00:00:00",
            "20.00",
        ],
    ]

    # patch 第二次 credit 调用让它抛异常
    import src.services.taobao_import as ti_module

    original_credit = ti_module.credit
    call_counter = {"n": 0}

    def boom(*args, **kwargs):
        call_counter["n"] += 1
        if call_counter["n"] == 2:
            raise RuntimeError("simulated db failure")
        return original_credit(*args, **kwargs)

    monkeypatch.setattr(ti_module, "credit", boom)

    # 启用 raise_server_exceptions=False 后,RuntimeError 转 500
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

    # 第一笔应该被 rollback,余额仍为 0
    assert _wallet_balance(shop.store_alipay_wallet_id) == Decimal("0.000000")

    db = database.SessionLocal()
    try:
        orders = db.scalars(select(TaobaoOrder)).all()
        assert orders == []
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 模拟样例 281 条数据规模
# ---------------------------------------------------------------------------


def test_large_sample_distribution(client):
    """根据 scripts/qianniu_sample.json 状态分布生成 281 条（丙火电玩），跑通且报告字段对账。

    分布:
    - 交易成功                 : 55  (received)
    - 卖家已发货,等待买家确认  : 181 (shipped_unconfirmed)
    - 等待买家付款             : 10  (skipped)
    - 交易关闭                 : 22  (closed)
    - 买家已付款,等待卖家发货  : 12  (skipped)
    """
    shop = _shop_by_name("丙火电玩")
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
        pay_time = (
            "2026-04-29 23:00:00"
            if status in ("交易成功", "卖家已发货，等待买家确认", "买家已付款,等待卖家发货")
            else ""
        )
        rows.append([
            order_no,
            f"P{idx:04d}",
            detail_fn(f"P{idx:04d}", str(amount)),
            str(amount),
            status,
            pay_time,
            "丙火电玩",
            ship_time,
            confirm_amount,
        ])

    # 55 received
    for i in range(55):
        add("交易成功", Decimal("100.00"), "alipay" if i % 2 == 0 else "wechat")
    # 181 shipped_unconfirmed
    for i in range(181):
        add("卖家已发货，等待买家确认", Decimal("50.00"), "alipay" if i % 2 == 0 else "wechat")
    # 10 pending pay
    for _ in range(10):
        add("等待买家付款", Decimal("0.00"))
    # 22 closed
    for _ in range(22):
        add("交易关闭", Decimal("0.00"))
    # 12 paid unshipped
    for _ in range(12):
        add("买家已付款,等待卖家发货", Decimal("30.00"))

    # 注：scripts/qianniu_sample.json 的 5 个状态计数和为 280；JSON 顶层 total_rows=281
    # 与之有 1 行差异（怀疑是空行或不在 5 状态枚举里的样本）。我们按状态分布精确测,
    # 这里行数应 = 280。
    assert len(rows) == 280
    response = _post_import(client, shop.id, _build_xlsx(rows))
    assert response.status_code == 200, response.text
    p = response.json()

    assert p["totalRowsParsed"] == 280
    # received(55) + shipped(181) + closed(22) 都建订单，pending+unshipped(22) 跳过
    assert p["createdOrders"] == 55 + 181 + 22
    assert p["skippedUnpaidOrUnshipped"] == 10 + 12
    assert p["skippedUnknownPayment"] == 0
    assert p["statusChangedOrders"] == 0
    assert p["closedReverted"] == 0
    assert p["errors"] == []
