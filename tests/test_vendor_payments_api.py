"""Tests for the dedicated vendor payment endpoint (POST /vendors/{id}/payment)."""
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from src import database
from src.main import app
from src.models.vendor import Vendor
from src.models.wallet import Wallet, credit, debit
from src.services.assets import ensure_default_asset_wallets


@pytest.fixture()
def client(tmp_path):
    database.configure_database(f"sqlite:///{tmp_path / 'vendor_payments.db'}")
    database.init_db()
    db = database.SessionLocal()
    try:
        ensure_default_asset_wallets(db)
        db.commit()
    finally:
        db.close()
    return TestClient(app)


def _find_wallet_id(wallets, name):
    for wallet in wallets:
        if wallet["name"] == name:
            return wallet["id"]
        found = _find_wallet_id(wallet.get("children", []), name)
        if found:
            return found
    return None


def _get_leaf_id(client, name):
    return _find_wallet_id(client.get("/wallets/assets").json(), name)


def _credit(client, wallet_id, amount):
    resp = client.post(f"/wallets/assets/{wallet_id}/credit", json={"amount": str(amount)})
    assert resp.status_code == 201, resp.text


def _create_vendor(client, name="供应商A"):
    resp = client.post("/vendors", json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _seed_vendor_balance(vendor_id, amount):
    """直接通过 wallet credit/debit 调整 vendor 钱包余额（绕过 router，仅用于测试 setup）"""
    db = database.SessionLocal()
    try:
        vendor = db.get(Vendor, vendor_id)
        amt = Decimal(str(amount))
        if amt > 0:
            credit(db, vendor.wallet_id, amt, "test seed")
        elif amt < 0:
            debit(db, vendor.wallet_id, abs(amt), "test seed")
        db.commit()
    finally:
        db.close()


def test_payment_same_currency_partial_settle(client):
    """vendor +1000，付 600 → vendor 余额 +400"""
    src_id = _get_leaf_id(client, "丙火网络支付宝")
    _credit(client, src_id, "5000")
    vendor = _create_vendor(client, name="供A")
    _seed_vendor_balance(vendor["id"], "1000")

    resp = client.post(
        f"/vendors/{vendor['id']}/payment",
        json={"from_wallet_id": src_id, "amount": "600"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert Decimal(body["exchange_rate"]) == Decimal("1")
    assert Decimal(body["from_wallet_balance"]) == Decimal("4400")
    assert Decimal(body["vendor_wallet_balance"]) == Decimal("400")
    assert body["from_transaction"]["direction"] == "out"
    assert body["vendor_transaction"]["direction"] == "out"


def test_payment_same_currency_full_settle(client):
    """vendor +1000，付 1000 → 0"""
    src_id = _get_leaf_id(client, "丙火网络支付宝")
    _credit(client, src_id, "5000")
    vendor = _create_vendor(client, name="供B")
    _seed_vendor_balance(vendor["id"], "1000")

    resp = client.post(
        f"/vendors/{vendor['id']}/payment",
        json={"from_wallet_id": src_id, "amount": "1000"},
    )
    assert resp.status_code == 200, resp.text
    assert Decimal(resp.json()["vendor_wallet_balance"]) == Decimal("0")


def test_payment_same_currency_overpay_becomes_prepaid(client):
    """vendor +1000，付 1500 → -500（预付）"""
    src_id = _get_leaf_id(client, "丙火网络支付宝")
    _credit(client, src_id, "5000")
    vendor = _create_vendor(client, name="供C")
    _seed_vendor_balance(vendor["id"], "1000")

    resp = client.post(
        f"/vendors/{vendor['id']}/payment",
        json={"from_wallet_id": src_id, "amount": "1500"},
    )
    assert resp.status_code == 200, resp.text
    assert Decimal(resp.json()["vendor_wallet_balance"]) == Decimal("-500")


def test_payment_same_currency_zero_to_prepaid(client):
    """vendor 0，付 500 → -500"""
    src_id = _get_leaf_id(client, "丙火网络支付宝")
    _credit(client, src_id, "5000")
    vendor = _create_vendor(client, name="供D")

    resp = client.post(
        f"/vendors/{vendor['id']}/payment",
        json={"from_wallet_id": src_id, "amount": "500"},
    )
    assert resp.status_code == 200, resp.text
    assert Decimal(resp.json()["vendor_wallet_balance"]) == Decimal("-500")
    assert Decimal(resp.json()["from_wallet_balance"]) == Decimal("4500")


def test_payment_cross_currency_usdt_to_cny(client):
    """USDT 付 100，rate=7.2 → vendor 减 720 CNY"""
    src_id = _get_leaf_id(client, "FREEMAN币安")  # USDT
    _credit(client, src_id, "1000")
    vendor = _create_vendor(client, name="供E")
    _seed_vendor_balance(vendor["id"], "1000")  # vendor +1000 CNY

    resp = client.post(
        f"/vendors/{vendor['id']}/payment",
        json={"from_wallet_id": src_id, "amount": "100", "exchange_rate": "7.2"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert Decimal(body["from_wallet_balance"]) == Decimal("900")
    assert Decimal(body["vendor_wallet_balance"]) == Decimal("280")  # 1000 - 720
    assert Decimal(body["from_transaction"]["amount"]) == Decimal("100")
    assert Decimal(body["vendor_transaction"]["amount"]) == Decimal("720")


def test_payment_insufficient_asset_balance_atomic(client):
    """from 余额不足 → 400 + DB 零变化"""
    src_id = _get_leaf_id(client, "丙火网络支付宝")
    _credit(client, src_id, "50")
    vendor = _create_vendor(client, name="供F")
    _seed_vendor_balance(vendor["id"], "1000")

    resp = client.post(
        f"/vendors/{vendor['id']}/payment",
        json={"from_wallet_id": src_id, "amount": "100"},
    )
    assert resp.status_code == 400

    db = database.SessionLocal()
    try:
        src = db.get(Wallet, src_id)
        v_wallet = db.get(Wallet, vendor["walletId"])
        assert Decimal(src.balance) == Decimal("50")
        assert Decimal(v_wallet.balance) == Decimal("1000")
    finally:
        db.close()


def test_payment_cross_currency_without_rate_returns_400(client):
    src_id = _get_leaf_id(client, "FREEMAN币安")  # USDT
    _credit(client, src_id, "1000")
    vendor = _create_vendor(client, name="供G")

    resp = client.post(
        f"/vendors/{vendor['id']}/payment",
        json={"from_wallet_id": src_id, "amount": "100"},
    )
    assert resp.status_code == 400
    assert "跨币种" in resp.json()["detail"]


def test_payment_from_non_asset_wallet_returns_400(client):
    """from 不是资产钱包（用另一个 vendor 钱包当 from）"""
    other_vendor = _create_vendor(client, name="非资产源")
    vendor = _create_vendor(client, name="供H")

    resp = client.post(
        f"/vendors/{vendor['id']}/payment",
        json={"from_wallet_id": other_vendor["walletId"], "amount": "100"},
    )
    assert resp.status_code == 400
    assert "只能从资产钱包付款" in resp.json()["detail"]


def test_payment_from_group_wallet_returns_400(client):
    """from 是分组（RMB钱包顶级）"""
    wallets = client.get("/wallets/assets").json()
    rmb_root_id = next(w["id"] for w in wallets if w["name"] == "RMB钱包")
    vendor = _create_vendor(client, name="供I")

    resp = client.post(
        f"/vendors/{vendor['id']}/payment",
        json={"from_wallet_id": rmb_root_id, "amount": "100"},
    )
    assert resp.status_code == 400
    assert "分组钱包" in resp.json()["detail"]


def test_payment_from_soft_deleted_wallet_returns_400(client):
    src_id = _get_leaf_id(client, "丙火网络支付宝")
    vendor = _create_vendor(client, name="供J")

    db = database.SessionLocal()
    try:
        from sqlalchemy import func as sa_func
        w = db.get(Wallet, src_id)
        w.deleted_at = sa_func.now()
        db.commit()
    finally:
        db.close()

    resp = client.post(
        f"/vendors/{vendor['id']}/payment",
        json={"from_wallet_id": src_id, "amount": "10"},
    )
    assert resp.status_code == 400
    assert "已删除" in resp.json()["detail"]


def test_payment_nonexistent_vendor_or_wallet_returns_404(client):
    src_id = _get_leaf_id(client, "丙火网络支付宝")
    _credit(client, src_id, "1000")

    # vendor 不存在
    resp = client.post(
        "/vendors/99999/payment",
        json={"from_wallet_id": src_id, "amount": "10"},
    )
    assert resp.status_code == 404
    assert "供应商不存在" in resp.json()["detail"]

    # from 钱包不存在
    vendor = _create_vendor(client, name="供K")
    resp = client.post(
        f"/vendors/{vendor['id']}/payment",
        json={"from_wallet_id": 99999, "amount": "10"},
    )
    assert resp.status_code == 404
    assert "源钱包不存在" in resp.json()["detail"]
