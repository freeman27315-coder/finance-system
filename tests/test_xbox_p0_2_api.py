"""XBOX P0.2 (issue #110) 测试：订单 / 销售记录 / 钱包设置 / 资金池联动。

CEO 2026-05-08 确认的方案：
- Q1A: 新建 ASSET_USD 钱包大类
- Q2A: 改 sale_price 自动 diff 调整钱包余额
- Q3A: 改 wallet_pool_id 旧池 debit + 新池 credit
- 销售记录不能撤销 + 合单按"账号+wallet_item_id"
- 多币种校验：sale_currency ↔ wallet_pool 钱包币种一致
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from src import database
from src.main import app
from src.models.wallet import Wallet, WalletType, create_wallet, Currency
from src.services.assets import ensure_default_asset_wallets


@pytest.fixture()
def client(tmp_path):
    database.configure_database(f"sqlite:///{tmp_path / 'xbox_p02.db'}")
    database.init_db()
    db = database.SessionLocal()
    try:
        ensure_default_asset_wallets(db)
        db.commit()
    finally:
        db.close()
    return TestClient(app)


def _get_pool_wallet_id(name: str) -> int:
    """找一个具体子钱包当资金池 (按 name 唯一定位)。"""
    db = database.SessionLocal()
    try:
        wallet = db.scalar(select(Wallet).where(Wallet.name == name))
        if wallet is None:
            raise AssertionError(f"未找到资金池钱包 {name}")
        return wallet.id
    finally:
        db.close()


def _create_account(client, account_no="P02-001"):
    r = client.post(
        "/xbox/accounts",
        json={"name": account_no, "country": "US", "accountNo": account_no, "exchangeRate": "7.20"},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _push_wallet_settings(client, items: list[dict]):
    """推送钱包设置（method "agent" + 自定义 items）。"""
    r = client.put(
        "/xbox/wallet-settings",
        json=[{"code": "agent", "label": "代理", "items": items}],
    )
    assert r.status_code == 200, r.text
    return r.json()


def _wallet_balance(wallet_id: int) -> Decimal:
    db = database.SessionLocal()
    try:
        w = db.get(Wallet, wallet_id)
        return Decimal(w.balance)
    finally:
        db.close()


# ----------------------------------------------------------
# 钱包设置同步 (FR-03 / IF-02)
# ----------------------------------------------------------

def test_wallet_settings_sync_creates_methods_and_items(client):
    pool_id = _get_pool_wallet_id("丙火网络支付宝")
    result = _push_wallet_settings(
        client,
        [{"code": "001", "label": "代理 001", "walletPoolId": pool_id}],
    )
    assert result["methods_upserted"] == 1
    assert result["items_upserted"] == 1

    r = client.get("/xbox/wallet-settings")
    assert r.status_code == 200
    methods = r.json()
    assert len(methods) == 1
    assert methods[0]["code"] == "agent"
    assert methods[0]["items"][0]["walletPoolId"] == pool_id


def test_wallet_settings_invalid_pool_returns_400(client):
    r = client.put(
        "/xbox/wallet-settings",
        json=[
            {"code": "agent", "label": "代理", "items": [
                {"code": "001", "label": "001", "walletPoolId": 99999}
            ]}
        ],
    )
    assert r.status_code == 400
    assert "不存在" in r.json()["detail"]


def test_wallet_settings_full_sync_disables_dropped_items(client):
    pool_id = _get_pool_wallet_id("丙火网络支付宝")
    # 第一次推 2 个 item
    _push_wallet_settings(
        client,
        [
            {"code": "001", "label": "代理 001", "walletPoolId": pool_id},
            {"code": "002", "label": "代理 002", "walletPoolId": pool_id},
        ],
    )
    # 第二次只推 001 → 002 应该 disable
    r2 = _push_wallet_settings(
        client,
        [{"code": "001", "label": "代理 001", "walletPoolId": pool_id}],
    )
    assert r2["items_disabled"] == 1

    r = client.get("/xbox/wallet-settings", params={"onlyActive": "false"})
    items = r.json()[0]["items"]
    by_code = {it["code"]: it for it in items}
    assert by_code["001"]["isActive"] is True
    assert by_code["002"]["isActive"] is False


# ----------------------------------------------------------
# 订单 (FR-04 + FR-05)
# ----------------------------------------------------------

def test_create_order_calculates_rmb_cost(client):
    account = _create_account(client)
    r = client.post(
        "/xbox/orders",
        json={
            "accountId": account["id"],
            "orderNo": "MS-001",
            "amountLocal": "100.00",
            "currencyLocal": "USD",
            "orderAt": "2026-05-08T10:00:00",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    # rmb_cost = 100 * 7.20 = 720
    assert Decimal(body["rmbCost"]) == Decimal("720.000000")
    assert Decimal(body["exchangeRate"]) == Decimal("7.20")
    assert body["status"] == "pending_complete"


def test_create_order_duplicate_no_returns_400(client):
    account = _create_account(client)
    body = {
        "accountId": account["id"],
        "orderNo": "DUP-1",
        "amountLocal": "10",
        "currencyLocal": "USD",
        "orderAt": "2026-05-08T10:00:00",
    }
    client.post("/xbox/orders", json=body)
    r = client.post("/xbox/orders", json=body)
    assert r.status_code == 400
    assert "已存在" in r.json()["detail"]


def test_complete_order_auto_converts_to_sale(client):
    """补齐订单全部字段 → 自动转销售记录 + credit 资金池。"""
    pool_id = _get_pool_wallet_id("丙火网络支付宝")
    _push_wallet_settings(
        client,
        [{"code": "001", "label": "代理 001", "walletPoolId": pool_id}],
    )
    method_id = client.get("/xbox/wallet-settings").json()[0]["id"]
    item_id = client.get("/xbox/wallet-settings").json()[0]["items"][0]["id"]

    account = _create_account(client)
    order = client.post(
        "/xbox/orders",
        json={
            "accountId": account["id"],
            "orderNo": "MS-100",
            "amountLocal": "100",
            "currencyLocal": "USD",
            "orderAt": "2026-05-08T10:00:00",
        },
    ).json()

    # 补齐字段（人民币售价 ¥800 进丙火支付宝资金池）
    assert _wallet_balance(pool_id) == Decimal("0")
    r = client.patch(
        f"/xbox/orders/{order['id']}",
        json={
            "saleDate": "2026-05-08",
            "productName": "Game A",
            "operatorName": "运营 A",
            "salePrice": "800.00",
            "saleCurrency": "CNY",
            "walletMethodId": method_id,
            "walletItemId": item_id,
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "converted"
    assert r.json()["saleRecordId"] is not None

    # 资金池余额 +800
    assert _wallet_balance(pool_id) == Decimal("800.000000")


def test_sale_currency_pool_currency_mismatch_returns_400(client):
    """销售币种 USD 但资金池是 RMB → 拒绝。"""
    pool_id = _get_pool_wallet_id("丙火网络支付宝")  # CNY
    _push_wallet_settings(
        client,
        [{"code": "001", "label": "代理 001", "walletPoolId": pool_id}],
    )
    method_id = client.get("/xbox/wallet-settings").json()[0]["id"]
    item_id = client.get("/xbox/wallet-settings").json()[0]["items"][0]["id"]

    account = _create_account(client)
    order = client.post(
        "/xbox/orders",
        json={"accountId": account["id"], "orderNo": "X-1", "amountLocal": "10",
              "currencyLocal": "USD", "orderAt": "2026-05-08T10:00:00"},
    ).json()
    r = client.patch(
        f"/xbox/orders/{order['id']}",
        json={
            "saleDate": "2026-05-08", "productName": "X", "operatorName": "X",
            "salePrice": "100", "saleCurrency": "USD",  # USD 但池子是 CNY
            "walletMethodId": method_id, "walletItemId": item_id,
        },
    )
    assert r.status_code == 400
    assert "不一致" in r.json()["detail"]


# ----------------------------------------------------------
# USD 销售流入 ASSET_USD（CEO Q1A）
# ----------------------------------------------------------

def test_usd_sale_flows_into_asset_usd_wallet(client):
    """USD 销售 → 自动新建 ASSET_USD 钱包大类下的子钱包应能当资金池。"""
    # 在 USD钱包 大类下建一个子钱包当资金池
    db = database.SessionLocal()
    try:
        usd_root = db.scalar(
            select(Wallet).where(Wallet.type == WalletType.ASSET_USD.value, Wallet.parent_id.is_(None))
        )
        assert usd_root is not None
        from src.services.assets import ensure_sub_wallet
        usd_pool = ensure_sub_wallet(db, usd_root, "代理USD池", is_group=False)
        usd_pool_id = usd_pool.id
        db.commit()
    finally:
        db.close()

    _push_wallet_settings(
        client,
        [{"code": "USD-001", "label": "代理 USD 001", "walletPoolId": usd_pool_id}],
    )
    method_id = client.get("/xbox/wallet-settings").json()[0]["id"]
    item_id = client.get("/xbox/wallet-settings").json()[0]["items"][0]["id"]

    account = _create_account(client)
    order = client.post(
        "/xbox/orders",
        json={"accountId": account["id"], "orderNo": "USD-1", "amountLocal": "100",
              "currencyLocal": "USD", "orderAt": "2026-05-08T10:00:00"},
    ).json()
    r = client.patch(
        f"/xbox/orders/{order['id']}",
        json={
            "saleDate": "2026-05-08", "productName": "P1", "operatorName": "Op",
            "salePrice": "120", "saleCurrency": "USD",  # USD 进 USD 池
            "walletMethodId": method_id, "walletItemId": item_id,
        },
    )
    assert r.status_code == 200
    assert _wallet_balance(usd_pool_id) == Decimal("120.000000")


# ----------------------------------------------------------
# 合单 (FR-06)
# ----------------------------------------------------------

def test_merge_orders_same_account_same_item_increments_sale_price(client):
    """同账号 + 同 wallet_item_id → 合单累加售价。"""
    pool_id = _get_pool_wallet_id("丙火网络支付宝")
    _push_wallet_settings(
        client,
        [{"code": "001", "label": "代理 001", "walletPoolId": pool_id}],
    )
    method_id = client.get("/xbox/wallet-settings").json()[0]["id"]
    item_id = client.get("/xbox/wallet-settings").json()[0]["items"][0]["id"]

    account = _create_account(client)

    def _create_and_complete(order_no: str, sale_price: str):
        order = client.post("/xbox/orders", json={
            "accountId": account["id"], "orderNo": order_no, "amountLocal": "10",
            "currencyLocal": "USD", "orderAt": "2026-05-08T10:00:00",
        }).json()
        return client.patch(f"/xbox/orders/{order['id']}", json={
            "saleDate": "2026-05-08", "productName": f"P-{order_no}",
            "operatorName": "Op", "salePrice": sale_price, "saleCurrency": "CNY",
            "walletMethodId": method_id, "walletItemId": item_id,
        }).json()

    r1 = _create_and_complete("MERGE-1", "1330")
    r2 = _create_and_complete("MERGE-2", "0")  # 叠加档（售价 0）
    r3 = _create_and_complete("MERGE-3", "200")

    # 都指向同一条销售记录
    assert r1["saleRecordId"] == r2["saleRecordId"] == r3["saleRecordId"]

    # 销售记录售价 = 1330 + 0 + 200 = 1530
    record_id = r1["saleRecordId"]
    records = client.get("/xbox/sale-records").json()
    record = next(r for r in records if r["id"] == record_id)
    assert Decimal(record["salePrice"]) == Decimal("1530.000000")

    # 资金池余额也是 1530
    assert _wallet_balance(pool_id) == Decimal("1530.000000")

    # 销售记录关联 3 个订单
    assert len(record["orderIds"]) == 3


# ----------------------------------------------------------
# 改销售记录字段（CEO Q2A 改售价 + Q3A 改资金池）
# ----------------------------------------------------------

def _setup_basic_sale(client):
    """通用 helper:建账号 + 设钱包 + 转一笔 ¥800 销售记录,返回相关 id。"""
    pool_a_id = _get_pool_wallet_id("丙火网络支付宝")
    pool_b_id = _get_pool_wallet_id("TOM支付宝")
    _push_wallet_settings(
        client,
        [
            {"code": "001", "label": "代理 001", "walletPoolId": pool_a_id},
            {"code": "002", "label": "代理 002", "walletPoolId": pool_b_id},
        ],
    )
    methods = client.get("/xbox/wallet-settings").json()
    method_id = methods[0]["id"]
    items = methods[0]["items"]
    item_a = next(it for it in items if it["code"] == "001")
    item_b = next(it for it in items if it["code"] == "002")

    account = _create_account(client)
    order = client.post("/xbox/orders", json={
        "accountId": account["id"], "orderNo": "EDIT-1", "amountLocal": "100",
        "currencyLocal": "USD", "orderAt": "2026-05-08T10:00:00",
    }).json()
    completed = client.patch(f"/xbox/orders/{order['id']}", json={
        "saleDate": "2026-05-08", "productName": "P1", "operatorName": "Op",
        "salePrice": "800", "saleCurrency": "CNY",
        "walletMethodId": method_id, "walletItemId": item_a["id"],
    }).json()
    return {
        "account_id": account["id"],
        "method_id": method_id,
        "item_a_id": item_a["id"],
        "item_b_id": item_b["id"],
        "pool_a_id": pool_a_id,
        "pool_b_id": pool_b_id,
        "sale_record_id": completed["saleRecordId"],
    }


def test_update_sale_price_diff_adjusts_pool(client):
    """改 sale_price 800 → 1000,资金池余额自动 +200。"""
    ctx = _setup_basic_sale(client)
    assert _wallet_balance(ctx["pool_a_id"]) == Decimal("800.000000")

    r = client.patch(
        f"/xbox/sale-records/{ctx['sale_record_id']}",
        json={"salePrice": "1000"},
    )
    assert r.status_code == 200, r.text
    assert Decimal(r.json()["salePrice"]) == Decimal("1000.000000")
    assert _wallet_balance(ctx["pool_a_id"]) == Decimal("1000.000000")


def test_update_sale_price_lower_debits_pool(client):
    """改 sale_price 800 → 500,资金池 -300。"""
    ctx = _setup_basic_sale(client)
    r = client.patch(
        f"/xbox/sale-records/{ctx['sale_record_id']}",
        json={"salePrice": "500"},
    )
    assert r.status_code == 200
    assert _wallet_balance(ctx["pool_a_id"]) == Decimal("500.000000")


def test_change_wallet_pool_debits_old_credits_new(client):
    """改 wallet_pool_id 旧池 debit 全额 + 新池 credit 全额。"""
    ctx = _setup_basic_sale(client)
    assert _wallet_balance(ctx["pool_a_id"]) == Decimal("800.000000")
    assert _wallet_balance(ctx["pool_b_id"]) == Decimal("0")

    r = client.patch(
        f"/xbox/sale-records/{ctx['sale_record_id']}",
        json={
            "walletItemId": ctx["item_b_id"],
            "walletItemLabel": "代理 002",
            "walletPoolId": ctx["pool_b_id"],
        },
    )
    assert r.status_code == 200, r.text

    assert _wallet_balance(ctx["pool_a_id"]) == Decimal("0.000000")
    assert _wallet_balance(ctx["pool_b_id"]) == Decimal("800.000000")
