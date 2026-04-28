from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from src import database
from src.main import app
from src.services.assets import ensure_default_asset_wallets


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


def test_create_and_list_vendors(client):
    vendor = create_vendor(client)

    response = client.get("/vendors")

    assert response.status_code == 200, response.text
    assert response.json()[0]["id"] == vendor["id"]
    assert response.json()[0]["name"] == "Vendor A"


def test_vendor_name_must_be_unique(client):
    create_vendor(client)

    response = client.post("/vendors", json={"name": "Vendor A"})

    assert response.status_code == 409


def test_create_list_and_settle_vendor_bills(client):
    vendor = create_vendor(client)

    payable = client.post(
        f"/vendors/{vendor['id']}/bills",
        json={
            "direction": "payable",
            "amount": "100.00",
            "due_date": "2026-05-01",
            "remark": "we owe vendor",
        },
    )
    receivable = client.post(
        f"/vendors/{vendor['id']}/bills",
        json={"direction": "receivable", "amount": "30.00", "remark": "vendor owes us"},
    )
    assert payable.status_code == 201, payable.text
    assert receivable.status_code == 201, receivable.text

    bills = client.get(f"/vendors/{vendor['id']}/bills")
    assert bills.status_code == 200, bills.text
    assert [bill["direction"] for bill in bills.json()] == ["payable", "receivable"]

    settled = client.patch(f"/vendors/bills/{payable.json()['id']}/settle")
    assert settled.status_code == 200, settled.text
    assert settled.json()["status"] == "settled"


def test_summary_counts_only_pending_bills(client):
    vendor = create_vendor(client)
    payable = client.post(
        f"/vendors/{vendor['id']}/bills",
        json={"direction": "payable", "amount": "100.00"},
    ).json()
    client.post(
        f"/vendors/{vendor['id']}/bills",
        json={"direction": "receivable", "amount": "40.00"},
    )

    summary = client.get("/vendors/summary")
    assert summary.status_code == 200, summary.text
    assert Decimal(summary.json()["payable"]) == Decimal("100.000000")
    assert Decimal(summary.json()["receivable"]) == Decimal("40.000000")
    assert Decimal(summary.json()["net"]) == Decimal("-60.000000")

    client.patch(f"/vendors/bills/{payable['id']}/settle")
    summary = client.get("/vendors/summary")
    assert Decimal(summary.json()["payable"]) == Decimal("0")
    assert Decimal(summary.json()["receivable"]) == Decimal("40.000000")
    assert Decimal(summary.json()["net"]) == Decimal("40.000000")
