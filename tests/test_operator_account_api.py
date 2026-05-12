"""客服 exe 端: 账号详情 + 同步 + 补销售信息 API (CEO 2026-05-12 PR-C)。"""
from __future__ import annotations

from decimal import Decimal

import pyotp
import pytest
from fastapi.testclient import TestClient

from src import database
from src.main import app
from src.models.wallet import Wallet, WalletType, Currency, create_wallet
from src.models.xbox import XboxWalletItem, XboxWalletMethod
from src.services.assets import ensure_default_asset_wallets


@pytest.fixture()
def client(tmp_path):
    database.configure_database(f"sqlite:///{tmp_path / 'operator_c.db'}")
    database.init_db()
    db = database.SessionLocal()
    try:
        ensure_default_asset_wallets(db)
        db.commit()
    finally:
        db.close()
    return TestClient(app)


# ---------------- 帮助函数 ----------------


def _create_operator(client, login_name, display_name=None, password="Pwd123456"):
    r = client.post(
        "/operator/operators",
        json={
            "loginName": login_name,
            "displayName": display_name or login_name,
            "password": password,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def _create_xbox_account(client, account_no="X-PR-C-001"):
    r = client.post(
        "/xbox/accounts",
        json={
            "name": account_no,
            "country": "US",
            "accountNo": account_no,
            "loginEmail": "x@test.com",
            "password": "MicrosoftPwd123",
            "exchangeRate": "7.2",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def _mark_available(client, account_id, available=True):
    r = client.patch(
        f"/xbox/accounts/{account_id}/availability",
        json={"isAvailableForClaim": available},
    )
    assert r.status_code == 200, r.text


def _claim(client, account_id, operator_id):
    r = client.post(
        "/operator/claims",
        json={"accountId": account_id, "operatorId": operator_id},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _ensure_wallet_setting(client) -> tuple[int, int, int]:
    """创建 1 个钱包池 + 1 个收款方式 + 1 个备注模板。返回 (pool_id, method_id, item_id)。"""
    db = database.SessionLocal()
    try:
        # 找一个 CNY 钱包(默认资产 RMB 主钱包)
        pool = db.scalars(
            db.query(Wallet).filter(Wallet.currency == Currency.CNY).order_by(Wallet.id).statement
        ).first()
        assert pool is not None
        method = XboxWalletMethod(code="test_method_pr_c", label="测试方式", is_active=True)
        db.add(method)
        db.flush()
        item = XboxWalletItem(
            method_id=method.id,
            code="test_item_pr_c",
            label="测试备注",
            wallet_pool_id=pool.id,
            is_active=True,
        )
        db.add(item)
        db.commit()
        return pool.id, method.id, item.id
    finally:
        db.close()


# ---------------- 账号详情 ----------------


def test_get_account_detail_includes_plaintext_password_and_balance(client):
    op = _create_operator(client, "detail_user")
    acc = _create_xbox_account(client, "DETAIL-1")
    _mark_available(client, acc["id"])
    _claim(client, acc["id"], op["operatorId"])

    r = client.get(
        f"/operator/accounts/{acc['id']}?operatorId={op['operatorId']}"
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["accountNo"] == "DETAIL-1"
    assert body["loginEmail"] == "x@test.com"
    # 关键: 密码明文必须解密返回(客服需要拿来登录 Microsoft)
    assert body["passwordPlain"] == "MicrosoftPwd123"
    assert body["localBalance"] == "0"
    assert body["status"] == "active"


def test_get_account_detail_forbidden_if_not_holder(client):
    op_a = _create_operator(client, "holder_a")
    op_b = _create_operator(client, "non_holder_b")
    acc = _create_xbox_account(client, "DETAIL-FORBID")
    _mark_available(client, acc["id"])
    _claim(client, acc["id"], op_a["operatorId"])

    # op_b 没领,不能看
    r = client.get(
        f"/operator/accounts/{acc['id']}?operatorId={op_b['operatorId']}"
    )
    assert r.status_code == 403
    assert "无权" in r.json()["detail"]


def test_get_account_detail_404_if_no_account(client):
    op = _create_operator(client, "ghost")
    r = client.get(f"/operator/accounts/999999?operatorId={op['operatorId']}")
    assert r.status_code == 404


# ---------------- 同步订单 ----------------


def test_sync_orders_by_operator_updates_balance(client):
    """客服触发同步: 调 trigger_sync, 更新账号余额, 写订单。"""
    op = _create_operator(client, "syncer")
    acc = _create_xbox_account(client, "SYNC-1")
    _mark_available(client, acc["id"])
    _claim(client, acc["id"], op["operatorId"])

    r = client.post(
        f"/operator/accounts/{acc['id']}/sync-orders",
        json={"operatorId": op["operatorId"], "count": 10},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert body["ordersAdded"] >= 1
    assert body["balance"] is not None

    # 账号余额更新了 (stub balance=123.45)
    detail = client.get(
        f"/operator/accounts/{acc['id']}?operatorId={op['operatorId']}"
    ).json()
    assert Decimal(detail["localBalance"]) == Decimal("123.45")


def test_sync_orders_forbidden_if_not_holder(client):
    op_a = _create_operator(client, "holder_sync_a")
    op_b = _create_operator(client, "non_holder_sync")
    acc = _create_xbox_account(client, "SYNC-FORBID")
    _mark_available(client, acc["id"])
    _claim(client, acc["id"], op_a["operatorId"])

    r = client.post(
        f"/operator/accounts/{acc['id']}/sync-orders",
        json={"operatorId": op_b["operatorId"], "count": 10},
    )
    assert r.status_code == 403


def test_sync_orders_invalid_count_400(client):
    op = _create_operator(client, "bad_count")
    acc = _create_xbox_account(client, "SYNC-BAD-COUNT")
    _mark_available(client, acc["id"])
    _claim(client, acc["id"], op["operatorId"])

    r = client.post(
        f"/operator/accounts/{acc['id']}/sync-orders",
        json={"operatorId": op["operatorId"], "count": 13},
    )
    assert r.status_code == 400


# ---------------- 订单列表 ----------------


def test_list_pending_orders_returns_synced_orders(client):
    op = _create_operator(client, "lister")
    acc = _create_xbox_account(client, "LIST-1")
    _mark_available(client, acc["id"])
    _claim(client, acc["id"], op["operatorId"])

    # 先同步出订单
    client.post(
        f"/operator/accounts/{acc['id']}/sync-orders",
        json={"operatorId": op["operatorId"], "count": 10},
    )
    r = client.get(
        f"/operator/accounts/{acc['id']}/orders?operatorId={op['operatorId']}"
    )
    assert r.status_code == 200
    orders = r.json()
    assert len(orders) >= 1
    # 默认只看待补的
    assert all(o["status"] == "pending_complete" for o in orders)
    # sale_date 已经自动 = order_at (CEO 2026-05-12 PR-A)
    for o in orders:
        assert o["saleDate"] == o["orderAt"]


def test_list_orders_forbidden_if_not_holder(client):
    op_a = _create_operator(client, "list_a")
    op_b = _create_operator(client, "list_b")
    acc = _create_xbox_account(client, "LIST-FORBID")
    _mark_available(client, acc["id"])
    _claim(client, acc["id"], op_a["operatorId"])

    r = client.get(
        f"/operator/accounts/{acc['id']}/orders?operatorId={op_b['operatorId']}"
    )
    assert r.status_code == 403


# ---------------- 补销售信息 ----------------


def test_complete_order_auto_fills_operator_name(client):
    """客服补销售: operatorName 自动 = 客服 display_name (CEO 2026-05-11)。"""
    op = _create_operator(client, "completer", display_name="李客服")
    acc = _create_xbox_account(client, "COMPLETE-1")
    _mark_available(client, acc["id"])
    _claim(client, acc["id"], op["operatorId"])

    # 同步出订单
    client.post(
        f"/operator/accounts/{acc['id']}/sync-orders",
        json={"operatorId": op["operatorId"], "count": 10},
    )
    orders = client.get(
        f"/operator/accounts/{acc['id']}/orders?operatorId={op['operatorId']}"
    ).json()
    order_id = orders[0]["id"]

    pool_id, method_id, item_id = _ensure_wallet_setting(client)

    r = client.patch(
        f"/operator/orders/{order_id}/completion",
        json={
            "operatorId": op["operatorId"],
            "productName": "5350 档",
            "salePrice": "5350",
            "saleCurrency": "CNY",
            "walletMethodId": method_id,
            "walletItemId": item_id,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["productName"] == "5350 档"
    assert Decimal(body["salePrice"]) == Decimal("5350")
    assert body["status"] == "converted"

    # 验证销售记录里 operator_name 自动是 "李客服"
    records = client.get("/xbox/sale-records").json()
    matching = [r for r in records if r["accountId"] == acc["id"]]
    assert len(matching) == 1
    assert matching[0]["operatorName"] == "李客服"


def test_complete_order_forbidden_if_not_holder(client):
    op_a = _create_operator(client, "comp_a")
    op_b = _create_operator(client, "comp_b")
    acc = _create_xbox_account(client, "COMP-FORBID")
    _mark_available(client, acc["id"])
    _claim(client, acc["id"], op_a["operatorId"])

    client.post(
        f"/operator/accounts/{acc['id']}/sync-orders",
        json={"operatorId": op_a["operatorId"], "count": 10},
    )
    orders = client.get(
        f"/operator/accounts/{acc['id']}/orders?operatorId={op_a['operatorId']}"
    ).json()
    order_id = orders[0]["id"]

    pool_id, method_id, item_id = _ensure_wallet_setting(client)

    r = client.patch(
        f"/operator/orders/{order_id}/completion",
        json={
            "operatorId": op_b["operatorId"],
            "productName": "x",
            "salePrice": "100",
            "saleCurrency": "CNY",
            "walletMethodId": method_id,
            "walletItemId": item_id,
        },
    )
    assert r.status_code == 403
