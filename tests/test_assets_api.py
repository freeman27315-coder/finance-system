from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from src import database
from src.main import app
from src.models.wallet import Currency, Wallet, WalletType, create_wallet
from src.services.assets import ensure_default_asset_wallets


@pytest.fixture()
def client(tmp_path):
    database.configure_database(f"sqlite:///{tmp_path / 'assets.db'}")
    database.init_db()
    db = database.SessionLocal()
    try:
        ensure_default_asset_wallets(db)
        db.commit()
    finally:
        db.close()
    return TestClient(app)


def _find_wallet(wallets, name):
    for wallet in wallets:
        if wallet["name"] == name:
            return wallet
        found = _find_wallet(wallet.get("children", []), name)
        if found:
            return found
    return None


def test_default_asset_wallets_are_listed(client):
    response = client.get("/wallets/assets")

    assert response.status_code == 200, response.text
    wallets = response.json()
    names = {wallet["name"] for wallet in wallets}
    assert {"RMB钱包", "USDT钱包"}.issubset(names)
    assert {wallet["currency"] for wallet in wallets} == {"CNY", "USDT"}
    assert all(wallet["parent_id"] is None for wallet in wallets)
    assert all(wallet["is_group"] for wallet in wallets)

    rmb = next(wallet for wallet in wallets if wallet["name"] == "RMB钱包")
    alipay = next(wallet for wallet in rmb["children"] if wallet["name"] == "支付宝钱包")
    wechat = next(wallet for wallet in rmb["children"] if wallet["name"] == "微信钱包")
    assert alipay["is_group"] is True
    assert wechat["is_group"] is True
    assert [wallet["name"] for wallet in alipay["children"]] == [
        "丙火网络支付宝",
        "TOM支付宝",
        "BOSS支付宝",
    ]
    assert [wallet["name"] for wallet in wechat["children"]] == ["跳舞姬微信"]

    usdt = next(wallet for wallet in wallets if wallet["name"] == "USDT钱包")
    assert [wallet["name"] for wallet in usdt["children"]] == ["FREEMAN币安", "张总币安"]
    assert all(not wallet["is_group"] for wallet in usdt["children"])


def test_existing_roots_are_migrated_without_duplicates(tmp_path):
    database.configure_database(f"sqlite:///{tmp_path / 'migration.db'}")
    database.init_db()
    db = database.SessionLocal()
    try:
        rmb = create_wallet(
            db,
            name="RMB Main",
            wallet_type=WalletType.ASSET_RMB,
            currency=Currency.CNY,
            opening_balance="10",
        )
        usdt = create_wallet(
            db,
            name="USDT Main",
            wallet_type=WalletType.ASSET_USDT,
            currency=Currency.USDT,
            opening_balance="5",
        )
        db.commit()

        ensure_default_asset_wallets(db)
        ensure_default_asset_wallets(db)
        db.commit()

        roots = list(
            db.scalars(
                select(Wallet)
                .where(Wallet.parent_id.is_(None), Wallet.type.in_(("ASSET_RMB", "ASSET_USDT")))
                .order_by(Wallet.id)
            )
        )
        assert [wallet.id for wallet in roots] == [rmb.id, usdt.id]
        assert [wallet.name for wallet in roots] == ["RMB钱包", "USDT钱包"]
        assert all(wallet.is_group for wallet in roots)
        assert all(wallet.balance == Decimal("0.000000") for wallet in roots)
        assert len(list(db.scalars(select(Wallet).where(Wallet.name == "支付宝钱包")))) == 1
    finally:
        db.close()


def test_create_sub_wallet_inherits_type_and_currency(client):
    root = client.get("/wallets/assets").json()[0]

    response = client.post(f"/wallets/assets/{root['id']}/sub", json={"name": "Operations"})

    assert response.status_code == 201, response.text
    sub_wallet = response.json()
    assert sub_wallet["name"] == "Operations"
    assert sub_wallet["type"] == root["type"]
    assert sub_wallet["currency"] == root["currency"]
    assert sub_wallet["parent_id"] == root["id"]
    assert sub_wallet["is_group"] is False

    wallets = client.get("/wallets/assets").json()
    assert _find_wallet(wallets, "Operations") is not None


def test_create_sub_wallet_can_create_group(client):
    root = client.get("/wallets/assets").json()[0]

    response = client.post(
        f"/wallets/assets/{root['id']}/sub",
        json={"name": "新分组", "is_group": True},
    )

    assert response.status_code == 201, response.text
    group = response.json()
    assert group["name"] == "新分组"
    assert group["is_group"] is True
    assert Decimal(group["balance"]) == Decimal("0.000000")


def test_credit_debit_and_transactions(client):
    wallets = client.get("/wallets/assets").json()
    leaf = _find_wallet(wallets, "丙火网络支付宝")
    assert leaf is not None

    response = client.post(
        f"/wallets/assets/{leaf['id']}/credit",
        json={"amount": "100.50", "remark": "initial deposit"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["direction"] == "in"

    response = client.post(
        f"/wallets/assets/{leaf['id']}/debit",
        json={"amount": "40.25", "remark": "payment"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["direction"] == "out"

    transactions = client.get(f"/wallets/assets/{leaf['id']}/transactions").json()
    assert [item["direction"] for item in transactions] == ["in", "out"]
    assert [Decimal(item["amount"]) for item in transactions] == [
        Decimal("100.500000"),
        Decimal("40.250000"),
    ]

    refreshed = client.get("/wallets/assets").json()
    rmb = _find_wallet(refreshed, "RMB钱包")
    alipay = _find_wallet(refreshed, "支付宝钱包")
    wallet = _find_wallet(refreshed, "丙火网络支付宝")
    assert Decimal(rmb["balance"]) == Decimal("60.250000")
    assert Decimal(alipay["balance"]) == Decimal("60.250000")
    assert Decimal(wallet["balance"]) == Decimal("60.250000")


def test_group_wallet_rejects_direct_credit(client):
    wallets = client.get("/wallets/assets").json()
    group = _find_wallet(wallets, "支付宝钱包")
    assert group is not None

    response = client.post(
        f"/wallets/assets/{group['id']}/credit",
        json={"amount": "1", "remark": "invalid"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "分组钱包不可直接记账，请操作叶子钱包"


def test_patch_wallet_updates_name(client):
    wallets = client.get("/wallets/assets").json()
    leaf = _find_wallet(wallets, "TOM支付宝")
    assert leaf is not None

    response = client.patch(
        f"/wallets/assets/{leaf['id']}",
        json={"name": "TOM支付宝（个人）"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["name"] == "TOM支付宝（个人）"

    refreshed = client.get("/wallets/assets").json()
    assert _find_wallet(refreshed, "TOM支付宝（个人）") is not None


def test_patch_wallet_updates_remark(client):
    wallets = client.get("/wallets/assets").json()
    leaf = _find_wallet(wallets, "BOSS支付宝")
    assert leaf is not None

    response = client.patch(
        f"/wallets/assets/{leaf['id']}",
        json={"remark": "用于公司日常报销"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["remark"] == "用于公司日常报销"


def test_patch_wallet_requires_at_least_one_field(client):
    wallets = client.get("/wallets/assets").json()
    leaf = _find_wallet(wallets, "BOSS支付宝")

    response = client.patch(f"/wallets/assets/{leaf['id']}", json={})

    assert response.status_code == 400


def test_delete_empty_leaf_wallet(client):
    wallets = client.get("/wallets/assets").json()
    leaf = _find_wallet(wallets, "BOSS支付宝")
    assert leaf is not None

    response = client.delete(f"/wallets/assets/{leaf['id']}")
    assert response.status_code == 204, response.text

    refreshed = client.get("/wallets/assets").json()
    assert _find_wallet(refreshed, "BOSS支付宝") is None

    full = client.get("/wallets/assets?include_deleted=true").json()
    deleted = _find_wallet(full, "BOSS支付宝")
    assert deleted is not None
    assert deleted["deleted_at"] is not None


def test_delete_rejects_wallet_with_balance(client):
    wallets = client.get("/wallets/assets").json()
    leaf = _find_wallet(wallets, "丙火网络支付宝")
    assert leaf is not None

    client.post(
        f"/wallets/assets/{leaf['id']}/credit",
        json={"amount": "10", "remark": "seed"},
    )

    response = client.delete(f"/wallets/assets/{leaf['id']}")
    assert response.status_code == 400
    assert response.json()["detail"] == "钱包余额非 0，请先全部出账"


def test_delete_rejects_top_level_wallet(client):
    wallets = client.get("/wallets/assets").json()
    rmb = next(wallet for wallet in wallets if wallet["name"] == "RMB钱包")

    response = client.delete(f"/wallets/assets/{rmb['id']}")
    assert response.status_code == 400
    assert response.json()["detail"] == "顶级钱包受保护"


def test_delete_rejects_group_with_active_children(client):
    wallets = client.get("/wallets/assets").json()
    alipay = _find_wallet(wallets, "支付宝钱包")
    assert alipay is not None

    response = client.delete(f"/wallets/assets/{alipay['id']}")
    assert response.status_code == 400
    assert response.json()["detail"] == "请先删除子钱包"


def test_credit_rejected_after_soft_delete(client):
    wallets = client.get("/wallets/assets").json()
    leaf = _find_wallet(wallets, "跳舞姬微信")
    assert leaf is not None

    delete_resp = client.delete(f"/wallets/assets/{leaf['id']}")
    assert delete_resp.status_code == 204, delete_resp.text

    response = client.post(
        f"/wallets/assets/{leaf['id']}/credit",
        json={"amount": "1", "remark": "should fail"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "已删除钱包不可记账"


def test_patch_rejected_after_soft_delete(client):
    wallets = client.get("/wallets/assets").json()
    leaf = _find_wallet(wallets, "张总币安")
    assert leaf is not None

    assert client.delete(f"/wallets/assets/{leaf['id']}").status_code == 204

    response = client.patch(
        f"/wallets/assets/{leaf['id']}",
        json={"name": "新名"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "已删除钱包不可编辑"


def test_debit_rejects_insufficient_balance(client):
    wallets = client.get("/wallets/assets").json()
    leaf = _find_wallet(wallets, "FREEMAN币安")
    assert leaf is not None

    response = client.post(
        f"/wallets/assets/{leaf['id']}/debit",
        json={"amount": "1", "remark": "too much"},
    )

    assert response.status_code == 400
    assert "insufficient" in response.json()["detail"]
