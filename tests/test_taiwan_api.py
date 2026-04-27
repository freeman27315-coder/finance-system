from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from src import database
from src.main import app
from src.services.assets import ensure_default_asset_wallets
from src.services.taiwan import ensure_default_taiwan_wallets


@pytest.fixture()
def client(tmp_path):
    database.configure_database(f"sqlite:///{tmp_path / 'taiwan.db'}")
    database.init_db()
    db = database.SessionLocal()
    try:
        ensure_default_asset_wallets(db)
        ensure_default_taiwan_wallets(db)
        db.commit()
    finally:
        db.close()
    return TestClient(app)


def test_default_taiwan_wallets_are_listed(client):
    response = client.get("/taiwan/wallets")

    assert response.status_code == 200, response.text
    wallets = response.json()
    assert {wallet["name"] for wallet in wallets} == {"8591 收入", "提现", "待处理"}
    assert {wallet["type"] for wallet in wallets} == {"TAIWAN"}
    assert {wallet["currency"] for wallet in wallets} == {"TWD"}


def test_credit_debit_transactions_and_summary(client):
    wallet = client.get("/taiwan/wallets").json()[0]

    credit = client.post(
        f"/taiwan/wallets/{wallet['id']}/credit",
        json={"amount": "500.00", "remark": "8591 income"},
    )
    debit = client.post(
        f"/taiwan/wallets/{wallet['id']}/debit",
        json={"amount": "120.00", "remark": "withdrawal"},
    )
    assert credit.status_code == 201, credit.text
    assert credit.json()["direction"] == "in"
    assert debit.status_code == 201, debit.text
    assert debit.json()["direction"] == "out"

    transactions = client.get(f"/taiwan/wallets/{wallet['id']}/transactions")
    assert transactions.status_code == 200, transactions.text
    assert [item["direction"] for item in transactions.json()] == ["in", "out"]

    summary = client.get("/taiwan/summary")
    assert summary.status_code == 200, summary.text
    assert Decimal(summary.json()["total_balance"]) == Decimal("380.000000")
    assert summary.json()["wallet_count"] == 3


def test_debit_rejects_insufficient_balance(client):
    wallet = client.get("/taiwan/wallets").json()[0]

    response = client.post(
        f"/taiwan/wallets/{wallet['id']}/debit",
        json={"amount": "1.00"},
    )

    assert response.status_code == 400
