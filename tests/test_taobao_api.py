from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from src import database
from src.main import app
from src.services.assets import ensure_default_asset_wallets


@pytest.fixture()
def client(tmp_path):
    database.configure_database(f"sqlite:///{tmp_path / 'taobao.db'}")
    database.init_db()
    db = database.SessionLocal()
    try:
        ensure_default_asset_wallets(db)
        db.commit()
    finally:
        db.close()
    return TestClient(app)


def create_account(client):
    response = client.post("/taobao/accounts", json={"name": "Taobao A", "remark": "store"})
    assert response.status_code == 201, response.text
    return response.json()


def test_create_account_creates_two_wallets(client):
    account = create_account(client)

    assert account["unsettled_wallet_id"] != account["settled_wallet_id"]
    assert Decimal(account["unsettled_balance"]) == Decimal("0.000000")
    assert Decimal(account["settled_balance"]) == Decimal("0.000000")

    response = client.get("/taobao/accounts")
    assert response.status_code == 200, response.text
    assert response.json()[0]["name"] == "Taobao A"


def test_taobao_credit_debit_and_transactions(client):
    account = create_account(client)

    unsettled = client.post(
        f"/taobao/accounts/{account['id']}/unsettled/credit",
        json={"amount": "120.00", "remark": "unsettled order"},
    )
    settled_credit = client.post(
        f"/taobao/accounts/{account['id']}/settled/credit",
        json={"amount": "80.00", "remark": "settled order"},
    )
    settled_debit = client.post(
        f"/taobao/accounts/{account['id']}/settled/debit",
        json={"amount": "30.00", "remark": "withdraw"},
    )

    assert unsettled.status_code == 201, unsettled.text
    assert unsettled.json()["wallet_scope"] == "unsettled"
    assert settled_credit.status_code == 201, settled_credit.text
    assert settled_credit.json()["wallet_scope"] == "settled"
    assert settled_debit.status_code == 201, settled_debit.text
    assert settled_debit.json()["direction"] == "out"

    transactions = client.get(f"/taobao/accounts/{account['id']}/transactions")
    assert transactions.status_code == 200, transactions.text
    assert [item["wallet_scope"] for item in transactions.json()] == [
        "unsettled",
        "settled",
        "settled",
    ]

    refreshed = client.get("/taobao/accounts").json()[0]
    assert Decimal(refreshed["unsettled_balance"]) == Decimal("120.000000")
    assert Decimal(refreshed["settled_balance"]) == Decimal("50.000000")


def test_settled_debit_rejects_insufficient_balance(client):
    account = create_account(client)

    response = client.post(
        f"/taobao/accounts/{account['id']}/settled/debit",
        json={"amount": "1.00"},
    )

    assert response.status_code == 400
