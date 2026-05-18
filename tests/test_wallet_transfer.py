"""Issue #129 - 划转单 (钱包间转账) 测试."""
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from src import database
from src.main import app
from src.models.wallet import Wallet
from src.services.assets import ensure_default_asset_wallets
from src.services.taiwan import ensure_default_taiwan_wallets


@pytest.fixture()
def client(tmp_path):
    database.configure_database(f"sqlite:///{tmp_path / 'wallet_transfer.db'}")
    database.init_db()
    db = database.SessionLocal()
    try:
        ensure_default_asset_wallets(db)
        ensure_default_taiwan_wallets(db)
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


def _get_asset_leaf_id(client, name):
    return _find_wallet_id(client.get("/wallets/assets").json(), name)


def _get_taiwan_wallet_id(client, name):
    for wallet in client.get("/taiwan/wallets").json():
        if wallet["name"] == name:
            return wallet["id"]
    return None


def _credit_asset(client, wallet_id, amount):
    resp = client.post(f"/wallets/assets/{wallet_id}/credit", json={"amount": str(amount)})
    assert resp.status_code == 201, resp.text


def _credit_taiwan(client, wallet_id, amount):
    resp = client.post(
        f"/taiwan/wallets/{wallet_id}/credit",
        json={"amount": str(amount), "remark": "test seed"},
    )
    assert resp.status_code == 201, resp.text


def _wallet_balance(wallet_id):
    db = database.SessionLocal()
    try:
        wallet = db.get(Wallet, wallet_id)
        return Decimal(wallet.balance)
    finally:
        db.close()


# ---- 1. 正向: 创建划转 → 两边余额变化, 汇率正确 ----


def test_create_transfer_changes_balances_and_records_rate(client):
    from_id = _get_asset_leaf_id(client, "丙火网络支付宝")
    to_id = _get_asset_leaf_id(client, "TOM支付宝")
    _credit_asset(client, from_id, "1000")

    resp = client.post(
        "/api/wallet-transfers",
        json={
            "from_wallet_id": from_id,
            "to_wallet_id": to_id,
            "from_amount": "300",
            "to_amount": "300",
            "operator_name": "freeman",
            "note": "test transfer",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert Decimal(body["from_amount"]) == Decimal("300")
    assert Decimal(body["to_amount"]) == Decimal("300")
    assert Decimal(body["rate"]) == Decimal("1")
    assert body["from_currency"] == "CNY"
    assert body["to_currency"] == "CNY"
    assert body["operator_name"] == "freeman"
    assert body["note"] == "test transfer"

    # 余额变化
    assert _wallet_balance(from_id) == Decimal("700")
    assert _wallet_balance(to_id) == Decimal("300")

    # 关联了 2 条流水, 一 OUT 一 IN
    assert len(body["transactions"]) == 2
    directions = {tx["direction"] for tx in body["transactions"]}
    assert directions == {"in", "out"}
    # 两条流水的 remark 都有"[划转]"前缀
    for tx in body["transactions"]:
        assert tx["remark"].startswith("[划转]")


# ---- 2. 同币种划转 (rate=1, 内部资金调拨) ----


def test_same_currency_transfer_rate_is_one(client):
    from_id = _get_taiwan_wallet_id(client, "全支付")
    to_id = _get_taiwan_wallet_id(client, "悠游付")
    _credit_taiwan(client, from_id, "5000")

    resp = client.post(
        "/api/wallet-transfers",
        json={
            "from_wallet_id": from_id,
            "to_wallet_id": to_id,
            "from_amount": "1000",
            "to_amount": "1000",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert Decimal(body["rate"]) == Decimal("1")
    assert body["from_currency"] == "TWD"
    assert body["to_currency"] == "TWD"
    assert _wallet_balance(from_id) == Decimal("4000")
    assert _wallet_balance(to_id) == Decimal("1000")


# ---- 3. 异币种划转 (TWD → USDT, 典型场景) ----


def test_cross_currency_transfer_twd_to_usdt(client):
    from_id = _get_taiwan_wallet_id(client, "全支付")  # TWD
    to_id = _get_asset_leaf_id(client, "FREEMAN币安")  # USDT
    _credit_taiwan(client, from_id, "30000")

    # 30000 TWD → 1000 USDT, rate = 1000 / 30000 = 0.03333333
    resp = client.post(
        "/api/wallet-transfers",
        json={
            "from_wallet_id": from_id,
            "to_wallet_id": to_id,
            "from_amount": "30000",
            "to_amount": "1000",
            "operator_name": "李睿旭",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["from_currency"] == "TWD"
    assert body["to_currency"] == "USDT"
    # rate = 1000 / 30000 = 0.03333333 (quantize 到 8 位小数)
    assert Decimal(body["rate"]) == Decimal("0.03333333")
    assert _wallet_balance(from_id) == Decimal("0")
    assert _wallet_balance(to_id) == Decimal("1000")


# ---- 4. 余额不足: from_wallet 余额不够 → 拒绝 ----


def test_insufficient_balance_rejected(client):
    from_id = _get_asset_leaf_id(client, "丙火网络支付宝")
    to_id = _get_asset_leaf_id(client, "TOM支付宝")
    _credit_asset(client, from_id, "100")  # 只有 100

    resp = client.post(
        "/api/wallet-transfers",
        json={
            "from_wallet_id": from_id,
            "to_wallet_id": to_id,
            "from_amount": "500",
            "to_amount": "500",
        },
    )
    assert resp.status_code == 400, resp.text
    assert "insufficient" in resp.json()["detail"].lower()

    # 原子性: from 没扣, to 没增
    assert _wallet_balance(from_id) == Decimal("100")
    assert _wallet_balance(to_id) == Decimal("0")

    # 列表里也不能出现这笔(已 rollback)
    listing = client.get("/api/wallet-transfers").json()
    assert listing == []


# ---- 5. 同钱包: from == to → 拒绝 ----


def test_same_wallet_rejected(client):
    wallet_id = _get_asset_leaf_id(client, "丙火网络支付宝")
    _credit_asset(client, wallet_id, "100")

    resp = client.post(
        "/api/wallet-transfers",
        json={
            "from_wallet_id": wallet_id,
            "to_wallet_id": wallet_id,
            "from_amount": "10",
            "to_amount": "10",
        },
    )
    assert resp.status_code == 400
    assert "同一个钱包" in resp.json()["detail"]


# ---- 6. 撤销: 余额回到原状 ----


def test_cancel_transfer_restores_balances(client):
    from_id = _get_asset_leaf_id(client, "丙火网络支付宝")
    to_id = _get_asset_leaf_id(client, "TOM支付宝")
    _credit_asset(client, from_id, "1000")

    # 先创建划转
    resp = client.post(
        "/api/wallet-transfers",
        json={
            "from_wallet_id": from_id,
            "to_wallet_id": to_id,
            "from_amount": "300",
            "to_amount": "300",
        },
    )
    assert resp.status_code == 201
    transfer_id = resp.json()["id"]
    assert _wallet_balance(from_id) == Decimal("700")
    assert _wallet_balance(to_id) == Decimal("300")

    # 撤销
    cancel_resp = client.delete(f"/api/wallet-transfers/{transfer_id}")
    assert cancel_resp.status_code == 200, cancel_resp.text
    body = cancel_resp.json()
    assert body["deleted_at"] is not None
    # 撤销后流水应该有 4 条 (原 OUT + 原 IN + 反向 OUT + 反向 IN)
    assert len(body["transactions"]) == 4

    # 余额回到原状
    assert _wallet_balance(from_id) == Decimal("1000")
    assert _wallet_balance(to_id) == Decimal("0")

    # 默认列表不含已撤销
    default_list = client.get("/api/wallet-transfers").json()
    assert all(t["id"] != transfer_id for t in default_list)
    # include_deleted=true 能看到
    full_list = client.get("/api/wallet-transfers?include_deleted=true").json()
    assert any(t["id"] == transfer_id for t in full_list)


# ---- 7. 撤销时 to 余额不足 → 拒绝 ----


def test_cancel_rejected_when_to_balance_insufficient(client):
    from_id = _get_asset_leaf_id(client, "丙火网络支付宝")
    to_id = _get_asset_leaf_id(client, "TOM支付宝")
    _credit_asset(client, from_id, "1000")

    # 划转 300 过去
    resp = client.post(
        "/api/wallet-transfers",
        json={
            "from_wallet_id": from_id,
            "to_wallet_id": to_id,
            "from_amount": "300",
            "to_amount": "300",
        },
    )
    transfer_id = resp.json()["id"]
    assert _wallet_balance(to_id) == Decimal("300")

    # to_wallet 把钱花掉到只剩 50
    debit_resp = client.post(
        f"/wallets/assets/{to_id}/debit", json={"amount": "250"}
    )
    assert debit_resp.status_code == 201
    assert _wallet_balance(to_id) == Decimal("50")

    # 撤销应该被拒绝(to 只有 50, 但要扣回 300)
    cancel_resp = client.delete(f"/api/wallet-transfers/{transfer_id}")
    assert cancel_resp.status_code == 400, cancel_resp.text
    assert "insufficient" in cancel_resp.json()["detail"].lower()

    # 余额没变, transfer 也没被软删
    assert _wallet_balance(from_id) == Decimal("700")
    assert _wallet_balance(to_id) == Decimal("50")
    get_resp = client.get(f"/api/wallet-transfers/{transfer_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["deleted_at"] is None


# ---- 额外: 创建时金额非正 / group 钱包 / 钱包不存在 ----


def test_create_transfer_rejects_non_positive_amount(client):
    from_id = _get_asset_leaf_id(client, "丙火网络支付宝")
    to_id = _get_asset_leaf_id(client, "TOM支付宝")
    _credit_asset(client, from_id, "100")

    # from_amount = 0 (被 pydantic gt=0 拦, 返回 422)
    resp = client.post(
        "/api/wallet-transfers",
        json={
            "from_wallet_id": from_id,
            "to_wallet_id": to_id,
            "from_amount": "0",
            "to_amount": "10",
        },
    )
    assert resp.status_code == 422


def test_create_transfer_rejects_group_wallet(client):
    # RMB钱包 是顶级 group
    wallets = client.get("/wallets/assets").json()
    rmb_root_id = next(w["id"] for w in wallets if w["name"] == "RMB钱包")
    leaf_id = _get_asset_leaf_id(client, "丙火网络支付宝")
    _credit_asset(client, leaf_id, "100")

    # group 作为 from
    resp = client.post(
        "/api/wallet-transfers",
        json={
            "from_wallet_id": rmb_root_id,
            "to_wallet_id": leaf_id,
            "from_amount": "10",
            "to_amount": "10",
        },
    )
    assert resp.status_code == 400
    assert "分组" in resp.json()["detail"]

    # group 作为 to
    resp = client.post(
        "/api/wallet-transfers",
        json={
            "from_wallet_id": leaf_id,
            "to_wallet_id": rmb_root_id,
            "from_amount": "10",
            "to_amount": "10",
        },
    )
    assert resp.status_code == 400
    assert "分组" in resp.json()["detail"]


def test_create_transfer_404_when_wallet_missing(client):
    leaf_id = _get_asset_leaf_id(client, "丙火网络支付宝")
    _credit_asset(client, leaf_id, "100")

    resp = client.post(
        "/api/wallet-transfers",
        json={
            "from_wallet_id": leaf_id,
            "to_wallet_id": 99999,
            "from_amount": "10",
            "to_amount": "10",
        },
    )
    assert resp.status_code == 404


# ---- 列表筛选 ----


def test_list_filters_by_wallet_and_operator(client):
    from_id = _get_asset_leaf_id(client, "丙火网络支付宝")
    to_id_1 = _get_asset_leaf_id(client, "TOM支付宝")
    to_id_2 = _get_asset_leaf_id(client, "BOSS支付宝")
    _credit_asset(client, from_id, "1000")

    client.post(
        "/api/wallet-transfers",
        json={
            "from_wallet_id": from_id,
            "to_wallet_id": to_id_1,
            "from_amount": "100",
            "to_amount": "100",
            "operator_name": "freeman",
        },
    )
    client.post(
        "/api/wallet-transfers",
        json={
            "from_wallet_id": from_id,
            "to_wallet_id": to_id_2,
            "from_amount": "200",
            "to_amount": "200",
            "operator_name": "李睿旭",
        },
    )

    # 按 to_wallet_id 筛
    resp = client.get(f"/api/wallet-transfers?to_wallet_id={to_id_1}")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["to_wallet_id"] == to_id_1

    # 按 operator 筛
    resp = client.get("/api/wallet-transfers?operator_name=freeman")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["operator_name"] == "freeman"


# ---- 双重撤销 ----


def test_double_cancel_rejected(client):
    from_id = _get_asset_leaf_id(client, "丙火网络支付宝")
    to_id = _get_asset_leaf_id(client, "TOM支付宝")
    _credit_asset(client, from_id, "1000")

    resp = client.post(
        "/api/wallet-transfers",
        json={
            "from_wallet_id": from_id,
            "to_wallet_id": to_id,
            "from_amount": "300",
            "to_amount": "300",
        },
    )
    transfer_id = resp.json()["id"]

    # 第一次撤销 ok
    assert client.delete(f"/api/wallet-transfers/{transfer_id}").status_code == 200
    # 第二次撤销拒绝
    second = client.delete(f"/api/wallet-transfers/{transfer_id}")
    assert second.status_code == 400
    assert "已撤销" in second.json()["detail"]
