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
