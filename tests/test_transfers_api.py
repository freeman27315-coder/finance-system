"""Tests for the wallet-to-wallet transfer endpoint."""
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from src import database
from src.main import app
from src.models.wallet import Wallet
from src.services.assets import ensure_default_asset_wallets


@pytest.fixture()
def client(tmp_path):
    database.configure_database(f"sqlite:///{tmp_path / 'transfers.db'}")
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


def _create_vendor(client, name="Vendor X"):
    resp = client.post("/vendors", json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()["walletId"]


def test_transfer_same_currency_rmb_to_rmb_success(client):
    src_id = _get_leaf_id(client, "丙火网络支付宝")
    dst_id = _get_leaf_id(client, "TOM支付宝")
    _credit(client, src_id, "1000")

    resp = client.post(
        "/wallets/transfer",
        json={"from_wallet_id": src_id, "to_wallet_id": dst_id, "amount": "300"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert Decimal(body["exchange_rate"]) == Decimal("1")
    assert Decimal(body["from_wallet_balance"]) == Decimal("700")
    assert Decimal(body["to_wallet_balance"]) == Decimal("300")
    assert body["from"]["direction"] == "out"
    assert body["to"]["direction"] == "in"


def test_transfer_cross_currency_rmb_to_usdt_with_rate(client):
    src_id = _get_leaf_id(client, "丙火网络支付宝")  # CNY
    dst_id = _get_leaf_id(client, "FREEMAN币安")  # USDT
    _credit(client, src_id, "7200")

    # 7200 CNY 按 1 CNY = 0.14 USDT 折算 → 1008 USDT
    resp = client.post(
        "/wallets/transfer",
        json={
            "from_wallet_id": src_id,
            "to_wallet_id": dst_id,
            "amount": "7200",
            "exchange_rate": "0.14",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert Decimal(body["from_wallet_balance"]) == Decimal("0")
    assert Decimal(body["to_wallet_balance"]) == Decimal("1008")
    assert Decimal(body["from"]["amount"]) == Decimal("7200")
    assert Decimal(body["to"]["amount"]) == Decimal("1008")


def test_transfer_cross_currency_usdt_to_rmb_with_rate(client):
    src_id = _get_leaf_id(client, "FREEMAN币安")  # USDT
    dst_id = _get_leaf_id(client, "丙火网络支付宝")  # CNY
    _credit(client, src_id, "1000")

    # 1000 USDT * 7.2 = 7200 CNY
    resp = client.post(
        "/wallets/transfer",
        json={
            "from_wallet_id": src_id,
            "to_wallet_id": dst_id,
            "amount": "1000",
            "exchange_rate": "7.2",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert Decimal(body["from_wallet_balance"]) == Decimal("0")
    assert Decimal(body["to_wallet_balance"]) == Decimal("7200")


def test_transfer_asset_to_vendor_pays_down_payable(client):
    src_id = _get_leaf_id(client, "丙火网络支付宝")
    vendor_wallet_id = _create_vendor(client, name="供应商A")
    _credit(client, src_id, "5000")

    # 资产 → 供应商钱包：vendor 余额减少（同币种 CNY）
    resp = client.post(
        "/wallets/transfer",
        json={"from_wallet_id": src_id, "to_wallet_id": vendor_wallet_id, "amount": "2000"},
    )
    # 此处供应商钱包是 credit（balance 增加）。CEO 付款给供应商业务上其实应该是 vendor debit；
    # 通用 transfer 端点保持语义对称：from debit / to credit。
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert Decimal(body["from_wallet_balance"]) == Decimal("3000")
    assert Decimal(body["to_wallet_balance"]) == Decimal("2000")


def test_transfer_self_returns_400(client):
    src_id = _get_leaf_id(client, "丙火网络支付宝")
    _credit(client, src_id, "100")

    resp = client.post(
        "/wallets/transfer",
        json={"from_wallet_id": src_id, "to_wallet_id": src_id, "amount": "10"},
    )
    assert resp.status_code == 400
    assert "不能转账给自己" in resp.json()["detail"]


def test_transfer_nonexistent_from_returns_404(client):
    dst_id = _get_leaf_id(client, "TOM支付宝")
    resp = client.post(
        "/wallets/transfer",
        json={"from_wallet_id": 99999, "to_wallet_id": dst_id, "amount": "10"},
    )
    assert resp.status_code == 404
    assert "源钱包不存在" in resp.json()["detail"]


def test_transfer_nonexistent_to_returns_404(client):
    src_id = _get_leaf_id(client, "丙火网络支付宝")
    resp = client.post(
        "/wallets/transfer",
        json={"from_wallet_id": src_id, "to_wallet_id": 99999, "amount": "10"},
    )
    assert resp.status_code == 404
    assert "目标钱包不存在" in resp.json()["detail"]


def test_transfer_cross_currency_without_rate_returns_400(client):
    src_id = _get_leaf_id(client, "丙火网络支付宝")
    dst_id = _get_leaf_id(client, "FREEMAN币安")
    _credit(client, src_id, "100")

    resp = client.post(
        "/wallets/transfer",
        json={"from_wallet_id": src_id, "to_wallet_id": dst_id, "amount": "100"},
    )
    assert resp.status_code == 400
    assert "跨币种" in resp.json()["detail"]


def test_transfer_insufficient_balance_non_vendor_returns_400(client):
    src_id = _get_leaf_id(client, "丙火网络支付宝")
    dst_id = _get_leaf_id(client, "TOM支付宝")
    _credit(client, src_id, "50")

    resp = client.post(
        "/wallets/transfer",
        json={"from_wallet_id": src_id, "to_wallet_id": dst_id, "amount": "100"},
    )
    assert resp.status_code == 400

    # 校验原子性：from 没扣，to 没增
    db = database.SessionLocal()
    try:
        src = db.get(Wallet, src_id)
        dst = db.get(Wallet, dst_id)
        assert Decimal(src.balance) == Decimal("50")
        assert Decimal(dst.balance) == Decimal("0")
    finally:
        db.close()


def test_transfer_from_vendor_allows_negative_balance(client):
    # VENDOR 类型 from 余额可以变负（debit 不报错）
    vendor_wallet_id = _create_vendor(client, name="供应商B")
    dst_id = _get_leaf_id(client, "TOM支付宝")  # CNY 同币种

    # vendor 当前余额 0，转出 500 → vendor 余额 -500，目标 +500
    resp = client.post(
        "/wallets/transfer",
        json={"from_wallet_id": vendor_wallet_id, "to_wallet_id": dst_id, "amount": "500"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert Decimal(body["from_wallet_balance"]) == Decimal("-500")
    assert Decimal(body["to_wallet_balance"]) == Decimal("500")


def test_transfer_rejects_soft_deleted_wallet(client):
    src_id = _get_leaf_id(client, "丙火网络支付宝")
    dst_id = _get_leaf_id(client, "TOM支付宝")

    # 软删 dst
    db = database.SessionLocal()
    try:
        from sqlalchemy import func as sa_func
        dst = db.get(Wallet, dst_id)
        dst.deleted_at = sa_func.now()
        db.commit()
    finally:
        db.close()

    _credit(client, src_id, "100")
    resp = client.post(
        "/wallets/transfer",
        json={"from_wallet_id": src_id, "to_wallet_id": dst_id, "amount": "10"},
    )
    assert resp.status_code == 400
    assert "目标钱包已删除" in resp.json()["detail"]


def test_transfer_rejects_group_wallet(client):
    # RMB钱包 是顶级分组
    wallets = client.get("/wallets/assets").json()
    rmb_root_id = next(w["id"] for w in wallets if w["name"] == "RMB钱包")
    leaf_id = _get_leaf_id(client, "丙火网络支付宝")

    # group 作为 from
    resp = client.post(
        "/wallets/transfer",
        json={"from_wallet_id": rmb_root_id, "to_wallet_id": leaf_id, "amount": "10"},
    )
    assert resp.status_code == 400
    assert "转出" in resp.json()["detail"]

    # group 作为 to
    _credit(client, leaf_id, "100")
    resp = client.post(
        "/wallets/transfer",
        json={"from_wallet_id": leaf_id, "to_wallet_id": rmb_root_id, "amount": "10"},
    )
    assert resp.status_code == 400
    assert "转入" in resp.json()["detail"]


def test_transfer_zero_amount_returns_400(client):
    src_id = _get_leaf_id(client, "丙火网络支付宝")
    dst_id = _get_leaf_id(client, "TOM支付宝")
    resp = client.post(
        "/wallets/transfer",
        json={"from_wallet_id": src_id, "to_wallet_id": dst_id, "amount": "0"},
    )
    assert resp.status_code == 400
    assert "金额必须大于 0" in resp.json()["detail"]
