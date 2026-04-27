from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from src import database
from src.main import app
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


def test_default_asset_wallets_are_listed(client):
    response = client.get("/wallets/assets")

    assert response.status_code == 200, response.text
    wallets = response.json()
    names = {wallet["name"] for wallet in wallets}
    assert {"RMB Main", "USDT Main"}.issubset(names)
    assert {wallet["currency"] for wallet in wallets} == {"CNY", "USDT"}
    assert all(wallet["parent_id"] is None for wallet in wallets)


def test_create_sub_wallet_inherits_type_and_currency(client):
    root = client.get("/wallets/assets").json()[0]

    response = client.post(f"/wallets/assets/{root['id']}/sub", json={"name": "Operations"})

    assert response.status_code == 201, response.text
    sub_wallet = response.json()
    assert sub_wallet["name"] == "Operations"
    assert sub_wallet["type"] == root["type"]
    assert sub_wallet["currency"] == root["currency"]
    assert sub_wallet["parent_id"] == root["id"]

    wallets = client.get("/wallets/assets").json()
    updated_root = next(wallet for wallet in wallets if wallet["id"] == root["id"])
    assert updated_root["children"][0]["name"] == "Operations"


def test_credit_debit_and_transactions(client):
    root = client.get("/wallets/assets").json()[0]

    response = client.post(
        f"/wallets/assets/{root['id']}/credit",
        json={"amount": "100.50", "remark": "initial deposit"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["direction"] == "in"

    response = client.post(
        f"/wallets/assets/{root['id']}/debit",
        json={"amount": "40.25", "remark": "payment"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["direction"] == "out"

    transactions = client.get(f"/wallets/assets/{root['id']}/transactions").json()
    assert [item["direction"] for item in transactions] == ["in", "out"]
    assert [Decimal(item["amount"]) for item in transactions] == [
        Decimal("100.500000"),
        Decimal("40.250000"),
    ]

    refreshed = client.get("/wallets/assets").json()
    wallet = next(item for item in refreshed if item["id"] == root["id"])
    assert Decimal(wallet["balance"]) == Decimal("60.250000")


def test_debit_rejects_insufficient_balance(client):
    root = client.get("/wallets/assets").json()[0]

    response = client.post(
        f"/wallets/assets/{root['id']}/debit",
        json={"amount": "1", "remark": "too much"},
    )

    assert response.status_code == 400
    assert "insufficient" in response.json()["detail"]
