"""淘宝 4 个金流端点 + 订单/钱包流水查询 测试。

覆盖：
- /aggregator/release：到期累计、无到期、防御性排除已撤流水
- /withdraw：可提现 → 银行卡 / 余额不足 / amount<=0
- /transfer-to-store-alipay：丙火 / 兔仔均成功 / amount 默认全额 / 银行卡空
- /orders：列表 + status/payment_method 过滤 + 分页 + 排序
- /wallets/{id}/transactions：mature_at 字段、wallet_id 校验
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
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
    debit,
)
from src.services.assets import ensure_default_asset_wallets
from src.services.taobao import ensure_default_taobao_wallets


@pytest.fixture()
def client(tmp_path):
    database.configure_database(f"sqlite:///{tmp_path / 'taobao_flow.db'}")
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


def _wallet_balance(wallet_id: int) -> Decimal:
    db = database.SessionLocal()
    try:
        w = db.get(Wallet, wallet_id)
        return Decimal(w.balance)
    finally:
        db.close()


def _seed_aggregator_frozen_tx(
    shop: TaobaoShop,
    amount: Decimal,
    mature_at: datetime,
    *,
    bind_to_order: bool = True,
    order_number: str | None = None,
) -> int:
    """直接往 aggregator_frozen 钱包注入一笔 in 流水，并视情况绑定到 TaobaoOrder。

    返回：插入的 WalletTransaction.id
    """
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
                status=TaobaoOrderStatus.RECEIVED.value,
                bookkeeping_wallet_id=shop.aggregator_frozen_wallet_id,
                bookkeeping_tx_id=tx.id,
            )
            db.add(order)
        db.commit()
        return tx.id
    finally:
        db.close()


# ---------------------------------------------------------------------------
# /aggregator/release
# ---------------------------------------------------------------------------


def test_release_aggregates_only_matured_transactions(client):
    """3 笔流水：2 笔已到期、1 笔未到期 → 仅解冻已到期金额。"""
    shop = _shop_by_name("丙火电玩")
    now = datetime.now(timezone.utc)

    _seed_aggregator_frozen_tx(shop, Decimal("100"), now - timedelta(days=1), order_number="MAT_1")
    _seed_aggregator_frozen_tx(shop, Decimal("50"), now - timedelta(hours=2), order_number="MAT_2")
    _seed_aggregator_frozen_tx(shop, Decimal("80"), now + timedelta(days=3), order_number="FUTURE_1")

    # 解冻前 frozen=230, available=0
    assert _wallet_balance(shop.aggregator_frozen_wallet_id) == Decimal("230.000000")
    assert _wallet_balance(shop.aggregator_available_wallet_id) == Decimal("0.000000")

    response = client.post(f"/taobao/shops/{shop.id}/aggregator/release")
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["maturedCount"] == 2
    assert Decimal(payload["maturedAmount"]) == Decimal("150")
    assert Decimal(payload["frozenBalanceAfter"]) == Decimal("80.000000")
    assert Decimal(payload["availableBalanceAfter"]) == Decimal("150.000000")

    # 数据库实际余额一致
    assert _wallet_balance(shop.aggregator_frozen_wallet_id) == Decimal("80.000000")
    assert _wallet_balance(shop.aggregator_available_wallet_id) == Decimal("150.000000")


def test_release_when_no_matured_returns_zero(client):
    """无到期流水时 200 + matured_count=0，不报错、不动余额。"""
    shop = _shop_by_name("丙火电玩")
    now = datetime.now(timezone.utc)
    _seed_aggregator_frozen_tx(shop, Decimal("99"), now + timedelta(days=2), order_number="FUT_ONLY")

    response = client.post(f"/taobao/shops/{shop.id}/aggregator/release")
    assert response.status_code == 200, response.text
    payload = response.json()

    assert payload["maturedCount"] == 0
    assert Decimal(payload["maturedAmount"]) == Decimal("0")
    assert Decimal(payload["frozenBalanceAfter"]) == Decimal("99.000000")
    assert Decimal(payload["availableBalanceAfter"]) == Decimal("0.000000")


def test_release_skips_orphan_matured_tx(client):
    """防御性：到期但已被 reconcile 撤掉（无 order 引用）的流水不应再被解冻。"""
    shop = _shop_by_name("丙火电玩")
    now = datetime.now(timezone.utc)

    # 流水 A：到期，绑订单
    _seed_aggregator_frozen_tx(shop, Decimal("200"), now - timedelta(days=1), order_number="ALIVE_A")
    # 流水 B：到期，但故意不绑订单（模拟已被撤）
    _seed_aggregator_frozen_tx(shop, Decimal("70"), now - timedelta(days=1), bind_to_order=False)

    response = client.post(f"/taobao/shops/{shop.id}/aggregator/release")
    assert response.status_code == 200
    payload = response.json()

    # 仅 A 被解冻
    assert payload["maturedCount"] == 1
    assert Decimal(payload["maturedAmount"]) == Decimal("200")


def test_release_404_when_shop_not_found(client):
    response = client.post("/taobao/shops/99999/aggregator/release")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# /withdraw
# ---------------------------------------------------------------------------


def test_withdraw_moves_available_to_bank_card(client):
    shop = _shop_by_name("丙火电玩")
    # 先种 200 到 available
    db = database.SessionLocal()
    try:
        credit(db, shop.aggregator_available_wallet_id, Decimal("200"), remark="种子")
        db.commit()
    finally:
        db.close()

    response = client.post(
        f"/taobao/shops/{shop.id}/withdraw",
        json={"amount": "120", "remark": "5月提现"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()

    assert Decimal(payload["amount"]) == Decimal("120")
    assert Decimal(payload["fromWalletBalance"]) == Decimal("80.000000")
    assert Decimal(payload["toWalletBalance"]) == Decimal("120.000000")
    assert payload["remark"] == "5月提现"

    assert _wallet_balance(shop.aggregator_available_wallet_id) == Decimal("80.000000")
    assert _wallet_balance(shop.bank_card_wallet_id) == Decimal("120.000000")


def test_withdraw_400_when_insufficient_balance(client):
    shop = _shop_by_name("丙火电玩")
    response = client.post(
        f"/taobao/shops/{shop.id}/withdraw",
        json={"amount": "100"},
    )
    assert response.status_code == 400
    assert "余额不足" in response.json()["detail"]


def test_withdraw_default_remark(client):
    shop = _shop_by_name("丙火电玩")
    db = database.SessionLocal()
    try:
        credit(db, shop.aggregator_available_wallet_id, Decimal("50"), remark="种子")
        db.commit()
    finally:
        db.close()

    response = client.post(
        f"/taobao/shops/{shop.id}/withdraw",
        json={"amount": "30"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["remark"] == "提现到银行卡"


def test_withdraw_404_when_shop_not_found(client):
    response = client.post("/taobao/shops/99999/withdraw", json={"amount": "1"})
    assert response.status_code == 404


def test_withdraw_400_when_amount_not_positive(client):
    """Pydantic gt=0 → 422，但 0 / 负数都被拦在前面。"""
    shop = _shop_by_name("丙火电玩")
    response = client.post(
        f"/taobao/shops/{shop.id}/withdraw",
        json={"amount": "0"},
    )
    assert response.status_code in (400, 422)


# ---------------------------------------------------------------------------
# /transfer-to-store-alipay
# ---------------------------------------------------------------------------


def test_transfer_to_store_alipay_a_shop_explicit_amount(client):
    """丙火电玩：bank_card → 丙火网络支付宝（资产支付宝子钱包），指定 amount。"""
    shop = _shop_by_name("丙火电玩")

    db = database.SessionLocal()
    try:
        credit(db, shop.bank_card_wallet_id, Decimal("500"), remark="种子")
        db.commit()
    finally:
        db.close()

    response = client.post(
        f"/taobao/shops/{shop.id}/transfer-to-store-alipay",
        json={"amount": "300"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()

    assert Decimal(payload["amount"]) == Decimal("300")
    assert Decimal(payload["fromWalletBalance"]) == Decimal("200.000000")
    assert Decimal(payload["toWalletBalance"]) == Decimal("300.000000")
    assert payload["remark"] == "提现"

    assert _wallet_balance(shop.bank_card_wallet_id) == Decimal("200.000000")
    assert _wallet_balance(shop.store_alipay_wallet_id) == Decimal("300.000000")


def test_transfer_to_store_alipay_b_shop_succeeds(client):
    """兔仔电玩：bank_card → 兔仔电玩支付宝（type=TAOBAO,账面记账）→ 成功。"""
    shop = _shop_by_name("兔仔电玩")

    db = database.SessionLocal()
    try:
        credit(db, shop.bank_card_wallet_id, Decimal("80"), remark="种子")
        db.commit()
    finally:
        db.close()

    response = client.post(
        f"/taobao/shops/{shop.id}/transfer-to-store-alipay",
        json={"amount": "30"},
    )
    assert response.status_code == 200, response.text
    payload = response.json()

    assert Decimal(payload["amount"]) == Decimal("30")
    assert Decimal(payload["fromWalletBalance"]) == Decimal("50.000000")
    assert Decimal(payload["toWalletBalance"]) == Decimal("30.000000")

    assert _wallet_balance(shop.bank_card_wallet_id) == Decimal("50.000000")
    assert _wallet_balance(shop.store_alipay_wallet_id) == Decimal("30.000000")


def test_transfer_to_store_alipay_default_amount_is_full_bank_balance(client):
    """amount 不传 → 默认转走银行卡全余额。"""
    shop = _shop_by_name("小小电玩")

    db = database.SessionLocal()
    try:
        credit(db, shop.bank_card_wallet_id, Decimal("777"), remark="种子")
        db.commit()
    finally:
        db.close()

    response = client.post(
        f"/taobao/shops/{shop.id}/transfer-to-store-alipay",
        json={},
    )
    assert response.status_code == 200, response.text
    payload = response.json()

    assert Decimal(payload["amount"]) == Decimal("777")
    assert Decimal(payload["fromWalletBalance"]) == Decimal("0.000000")
    assert Decimal(payload["toWalletBalance"]) == Decimal("777.000000")


def test_transfer_to_store_alipay_400_when_bank_card_empty(client):
    """银行卡余额为 0 时 amount 默认 0 → 400。"""
    shop = _shop_by_name("丙火电玩")
    response = client.post(
        f"/taobao/shops/{shop.id}/transfer-to-store-alipay",
        json={},
    )
    assert response.status_code == 400


def test_transfer_to_store_alipay_custom_remark(client):
    shop = _shop_by_name("丙火电玩")
    db = database.SessionLocal()
    try:
        credit(db, shop.bank_card_wallet_id, Decimal("100"), remark="种子")
        db.commit()
    finally:
        db.close()

    response = client.post(
        f"/taobao/shops/{shop.id}/transfer-to-store-alipay",
        json={"amount": "50", "remark": "5月转资产"},
    )
    assert response.status_code == 200
    assert response.json()["remark"] == "5月转资产"


# ---------------------------------------------------------------------------
# /orders
# ---------------------------------------------------------------------------


def _seed_orders(shop: TaobaoShop) -> None:
    """灌入 4 个不同状态/支付方式组合的订单。"""
    db = database.SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        rows = [
            ("ORD_AS_1", TaobaoOrderPaymentMethod.ALIPAY, TaobaoOrderStatus.SHIPPED_UNCONFIRMED, now - timedelta(hours=4)),
            ("ORD_AR_1", TaobaoOrderPaymentMethod.ALIPAY, TaobaoOrderStatus.RECEIVED, now - timedelta(hours=3)),
            ("ORD_WS_1", TaobaoOrderPaymentMethod.WECHAT, TaobaoOrderStatus.SHIPPED_UNCONFIRMED, now - timedelta(hours=2)),
            ("ORD_C_1", TaobaoOrderPaymentMethod.ALIPAY, TaobaoOrderStatus.CLOSED, now - timedelta(hours=1)),
        ]
        for order_number, method, st, synced in rows:
            order = TaobaoOrder(
                shop_id=shop.id,
                order_number=order_number,
                payment_method=method.value,
                amount=Decimal("10"),
                status=st.value,
                last_synced_at=synced,
            )
            db.add(order)
        db.commit()
    finally:
        db.close()


def test_list_orders_returns_all_for_shop_sorted_desc(client):
    shop = _shop_by_name("丙火电玩")
    _seed_orders(shop)

    response = client.get(f"/taobao/shops/{shop.id}/orders")
    assert response.status_code == 200, response.text
    orders = response.json()

    assert len(orders) == 4
    # 排序：last_synced_at desc → CLOSED 最新 → 第一
    assert orders[0]["orderNumber"] == "ORD_C_1"
    assert orders[-1]["orderNumber"] == "ORD_AS_1"


def test_list_orders_filter_by_status(client):
    shop = _shop_by_name("丙火电玩")
    _seed_orders(shop)

    response = client.get(
        f"/taobao/shops/{shop.id}/orders",
        params={"status": "received"},
    )
    assert response.status_code == 200
    orders = response.json()
    assert len(orders) == 1
    assert orders[0]["orderNumber"] == "ORD_AR_1"
    assert orders[0]["status"] == "received"


def test_list_orders_filter_by_payment_method(client):
    shop = _shop_by_name("丙火电玩")
    _seed_orders(shop)

    response = client.get(
        f"/taobao/shops/{shop.id}/orders",
        params={"payment_method": "wechat"},
    )
    assert response.status_code == 200
    orders = response.json()
    assert len(orders) == 1
    assert orders[0]["orderNumber"] == "ORD_WS_1"


def test_list_orders_pagination(client):
    shop = _shop_by_name("丙火电玩")
    _seed_orders(shop)

    response = client.get(
        f"/taobao/shops/{shop.id}/orders",
        params={"limit": 2, "offset": 1},
    )
    assert response.status_code == 200
    orders = response.json()
    assert len(orders) == 2


def test_list_orders_400_on_invalid_status(client):
    shop = _shop_by_name("丙火电玩")
    response = client.get(
        f"/taobao/shops/{shop.id}/orders",
        params={"status": "BOGUS"},
    )
    assert response.status_code == 400


def test_list_orders_404_when_shop_not_found(client):
    response = client.get("/taobao/shops/99999/orders")
    assert response.status_code == 404


def test_list_orders_isolated_by_shop(client):
    """丙火店的订单不会出现在小小店的列表里。"""
    binghuo = _shop_by_name("丙火电玩")
    xiaoxiao = _shop_by_name("小小电玩")
    _seed_orders(binghuo)

    response = client.get(f"/taobao/shops/{xiaoxiao.id}/orders")
    assert response.status_code == 200
    assert response.json() == []


# ---------------------------------------------------------------------------
# /wallets/{wallet_id}/transactions
# ---------------------------------------------------------------------------


def test_wallet_transactions_returns_mature_at(client):
    shop = _shop_by_name("丙火电玩")
    now = datetime.now(timezone.utc)
    _seed_aggregator_frozen_tx(shop, Decimal("100"), now + timedelta(days=5), order_number="MAT_TX_1")

    response = client.get(
        f"/taobao/shops/{shop.id}/wallets/{shop.aggregator_frozen_wallet_id}/transactions"
    )
    assert response.status_code == 200, response.text
    txs = response.json()
    assert len(txs) == 1
    tx = txs[0]
    assert tx["walletId"] == shop.aggregator_frozen_wallet_id
    assert Decimal(tx["amount"]) == Decimal("100")
    assert tx["direction"] == "in"
    assert tx["matureAt"] is not None


def test_wallet_transactions_404_when_wallet_not_in_shop(client):
    """随便挑一个非该店铺的 wallet_id → 404。"""
    shop = _shop_by_name("丙火电玩")
    other = _shop_by_name("小小电玩")
    other_wallet_id = other.bank_card_wallet_id
    assert other_wallet_id not in {
        shop.unconfirmed_alipay_wallet_id,
        shop.unconfirmed_wechat_wallet_id,
        shop.aggregator_frozen_wallet_id,
        shop.aggregator_available_wallet_id,
        shop.bank_card_wallet_id,
        shop.store_alipay_wallet_id,
    }
    response = client.get(
        f"/taobao/shops/{shop.id}/wallets/{other_wallet_id}/transactions"
    )
    assert response.status_code == 404


def test_wallet_transactions_store_alipay_wallet_allowed(client):
    """store_alipay_wallet（店铺支付宝）也应被允许查询。"""
    shop = _shop_by_name("丙火电玩")
    # 先 credit 到 store_alipay_wallet
    db = database.SessionLocal()
    try:
        credit(db, shop.store_alipay_wallet_id, Decimal("88"), remark="测试支付宝入账")
        db.commit()
    finally:
        db.close()

    response = client.get(
        f"/taobao/shops/{shop.id}/wallets/{shop.store_alipay_wallet_id}/transactions"
    )
    assert response.status_code == 200
    txs = response.json()
    assert len(txs) == 1
    assert Decimal(txs[0]["amount"]) == Decimal("88")
    assert txs[0]["matureAt"] is None


def test_wallet_transactions_404_when_shop_not_found(client):
    shop = _shop_by_name("丙火电玩")
    response = client.get(
        f"/taobao/shops/99999/wallets/{shop.aggregator_frozen_wallet_id}/transactions"
    )
    assert response.status_code == 404


def test_wallet_transactions_pagination_and_desc(client):
    """流水按 id desc 倒序 + 分页。"""
    shop = _shop_by_name("丙火电玩")
    db = database.SessionLocal()
    try:
        for i in range(5):
            credit(db, shop.bank_card_wallet_id, Decimal("10"), remark=f"种子 {i}")
        db.commit()
    finally:
        db.close()

    response = client.get(
        f"/taobao/shops/{shop.id}/wallets/{shop.bank_card_wallet_id}/transactions",
        params={"limit": 2, "offset": 0},
    )
    assert response.status_code == 200
    txs = response.json()
    assert len(txs) == 2
    # id desc：第一条是最新（最大 id）
    assert txs[0]["id"] > txs[1]["id"]
