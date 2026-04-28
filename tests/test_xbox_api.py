from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from src import database
from src.main import app
from src.services.assets import ensure_default_asset_wallets


@pytest.fixture()
def client(tmp_path):
    database.configure_database(f"sqlite:///{tmp_path / 'xbox.db'}")
    database.init_db()
    db = database.SessionLocal()
    try:
        ensure_default_asset_wallets(db)
        db.commit()
    finally:
        db.close()
    return TestClient(app)


def create_account(client, name="US Account", country="US"):
    response = client.post("/xbox/accounts", json={"name": name, "country": country})
    assert response.status_code == 201, response.text
    return response.json()


def test_create_and_filter_accounts(client):
    us_account = create_account(client, "US Account", "US")
    uk_account = create_account(client, "UK Account", "UK")

    assert us_account["currency"] == "USD"
    assert uk_account["currency"] == "GBP"

    response = client.get("/xbox/accounts", params={"country": "US"})
    assert response.status_code == 200, response.text
    assert [account["name"] for account in response.json()] == ["US Account"]


def test_recharge_consume_and_transactions(client):
    account = create_account(client)

    recharge = client.post(
        f"/xbox/accounts/{account['id']}/recharge",
        json={"rmb_amount": "700.00", "local_amount": "100.00", "remark": "USD top-up"},
    )
    assert recharge.status_code == 201, recharge.text
    assert recharge.json()["type"] == "recharge"

    consume = client.post(
        f"/xbox/accounts/{account['id']}/consume",
        json={"local_amount": "35.50", "remark": "game purchase"},
    )
    assert consume.status_code == 201, consume.text
    assert consume.json()["type"] == "consume"
    assert Decimal(consume.json()["rmb_amount"]) == Decimal("0.000000")

    transactions = client.get(f"/xbox/accounts/{account['id']}/transactions")
    assert transactions.status_code == 200, transactions.text
    assert [item["type"] for item in transactions.json()] == ["recharge", "consume"]

    refreshed = client.get("/xbox/accounts", params={"country": "US"}).json()[0]
    assert Decimal(refreshed["rmb_cost"]) == Decimal("700.000000")
    assert Decimal(refreshed["local_balance"]) == Decimal("64.500000")


def test_consume_rejects_insufficient_local_balance(client):
    account = create_account(client)

    response = client.post(
        f"/xbox/accounts/{account['id']}/consume",
        json={"local_amount": "1.00"},
    )

    assert response.status_code == 400


def test_summary_groups_usd_and_gbp(client):
    us_account = create_account(client, "US Account", "US")
    uk_account = create_account(client, "UK Account", "UK")
    client.post(
        f"/xbox/accounts/{us_account['id']}/recharge",
        json={"rmb_amount": "700.00", "local_amount": "100.00"},
    )
    client.post(
        f"/xbox/accounts/{uk_account['id']}/recharge",
        json={"rmb_amount": "900.00", "local_amount": "80.00"},
    )

    summary = client.get("/xbox/summary")

    assert summary.status_code == 200, summary.text
    assert Decimal(summary.json()["USD"]["rmb_cost"]) == Decimal("700.000000")
    assert Decimal(summary.json()["USD"]["local_balance"]) == Decimal("100.000000")
    assert Decimal(summary.json()["GBP"]["rmb_cost"]) == Decimal("900.000000")
    assert Decimal(summary.json()["GBP"]["local_balance"]) == Decimal("80.000000")
