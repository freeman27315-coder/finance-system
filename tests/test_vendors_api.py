from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from src import database
from src.main import app
from src.models.vendor import Vendor
from src.models.wallet import Wallet, WalletType
from src.services.assets import ensure_default_asset_wallets
from src.services.vendors import ensure_vendor_wallets


@pytest.fixture()
def client(tmp_path):
    database.configure_database(f"sqlite:///{tmp_path / 'vendors.db'}")
    database.init_db()
    db = database.SessionLocal()
    try:
        ensure_default_asset_wallets(db)
        db.commit()
    finally:
        db.close()
    return TestClient(app)


def create_vendor(client, name="Vendor A"):
    response = client.post("/vendors", json={"name": name, "remark": "trusted"})
    assert response.status_code == 201, response.text
    return response.json()


def test_create_vendor_returns_wallet_and_zero_balance(client):
    vendor = create_vendor(client)

    assert vendor["name"] == "Vendor A"
    assert vendor["walletId"] > 0
    assert Decimal(vendor["balance"]) == Decimal("0")


def test_list_vendors_returns_wallet_metadata(client):
    created = create_vendor(client)

    response = client.get("/vendors")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["id"] == created["id"]
    assert payload[0]["walletId"] == created["walletId"]
    assert Decimal(payload[0]["balance"]) == Decimal("0")


def test_vendor_name_must_be_unique(client):
    create_vendor(client)

    response = client.post("/vendors", json={"name": "Vendor A"})

    assert response.status_code == 409


def test_each_vendor_gets_its_own_vendor_wallet(client):
    a = create_vendor(client, name="Vendor A")
    b = create_vendor(client, name="Vendor B")
    c = create_vendor(client, name="Vendor C")

    wallet_ids = {a["walletId"], b["walletId"], c["walletId"]}
    assert len(wallet_ids) == 3

    db = database.SessionLocal()
    try:
        wallets = db.scalars(
            select(Wallet).where(Wallet.id.in_(wallet_ids))
        ).all()
        for wallet in wallets:
            wallet_type = wallet.type.value if hasattr(wallet.type, "value") else wallet.type
            assert wallet_type == WalletType.VENDOR.value
            assert wallet.currency.value if hasattr(wallet.currency, "value") else wallet.currency
            assert wallet.balance == Decimal("0")
            assert wallet.is_group is False
            assert wallet.parent_id is None
    finally:
        db.close()


def test_adjust_positive_increases_balance(client):
    vendor = create_vendor(client)

    response = client.post(
        f"/vendors/{vendor['id']}/adjust",
        json={"amount": "1000", "remark": "+1000 群指令"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert Decimal(payload["balance"]) == Decimal("1000")


def test_adjust_negative_decreases_balance_can_go_negative(client):
    vendor = create_vendor(client)

    response = client.post(
        f"/vendors/{vendor['id']}/adjust",
        json={"amount": "-500", "remark": "-500 已预付"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert Decimal(payload["balance"]) == Decimal("-500")


def test_adjust_zero_returns_400(client):
    vendor = create_vendor(client)

    response = client.post(
        f"/vendors/{vendor['id']}/adjust",
        json={"amount": "0"},
    )

    assert response.status_code == 400
    assert "0" in response.json()["detail"]


def test_adjust_unknown_vendor_returns_404(client):
    response = client.post(
        "/vendors/9999/adjust",
        json={"amount": "100"},
    )

    assert response.status_code == 404


def test_transactions_returned_in_reverse_chronological_order(client):
    vendor = create_vendor(client)

    client.post(f"/vendors/{vendor['id']}/adjust", json={"amount": "100", "remark": "first"})
    client.post(f"/vendors/{vendor['id']}/adjust", json={"amount": "-30", "remark": "second"})
    client.post(f"/vendors/{vendor['id']}/adjust", json={"amount": "50", "remark": "third"})

    response = client.get(f"/vendors/{vendor['id']}/transactions")

    assert response.status_code == 200, response.text
    txs = response.json()
    assert len(txs) == 3
    # 倒序：third 在最前
    assert txs[0]["remark"] == "third"
    assert txs[0]["direction"] == "in"
    assert Decimal(txs[0]["amount"]) == Decimal("50")
    assert txs[1]["remark"] == "second"
    assert txs[1]["direction"] == "out"
    assert Decimal(txs[1]["amount"]) == Decimal("30")
    assert txs[2]["remark"] == "first"
    assert txs[2]["direction"] == "in"


def test_transactions_unknown_vendor_returns_404(client):
    response = client.get("/vendors/9999/transactions")
    assert response.status_code == 404


def test_ensure_vendor_wallets_is_idempotent(client):
    create_vendor(client, name="Vendor A")
    create_vendor(client, name="Vendor B")

    db = database.SessionLocal()
    try:
        wallet_count_before = len(db.scalars(select(Wallet).where(Wallet.type == WalletType.VENDOR.value)).all())
        ensure_vendor_wallets(db)
        ensure_vendor_wallets(db)
        db.commit()
        wallet_count_after = len(db.scalars(select(Wallet).where(Wallet.type == WalletType.VENDOR.value)).all())
        assert wallet_count_before == wallet_count_after

        # 每个 vendor 仍有 wallet_id
        vendors = db.scalars(select(Vendor)).all()
        assert all(v.wallet_id is not None for v in vendors)
    finally:
        db.close()
