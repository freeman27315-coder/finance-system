"""Tests for the gift-card load endpoint (POST /vendors/{id}/giftcard-load)."""
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from src import database
from src.main import app
from src.services.assets import ensure_default_asset_wallets


@pytest.fixture()
def client(tmp_path):
    database.configure_database(f"sqlite:///{tmp_path / 'giftcard_load.db'}")
    database.init_db()
    db = database.SessionLocal()
    try:
        ensure_default_asset_wallets(db)
        db.commit()
    finally:
        db.close()
    return TestClient(app)


def _create_vendor(client, name="供应商X"):
    resp = client.post("/vendors", json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _create_xbox(client, name="FREEMAN", country="US"):
    resp = client.post("/xbox/accounts", json={"name": name, "country": country})
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_giftcard_load_success(client):
    """加载 USD 100 / RMB 700 → XBOX 账号 local_balance + rmb_cost + vendor 余额三方变化"""
    vendor = _create_vendor(client, name="供A")
    xbox = _create_xbox(client, name="FREEMAN-US", country="US")

    resp = client.post(
        f"/vendors/{vendor['id']}/giftcard-load",
        json={
            "xbox_account_id": xbox["id"],
            "card_face_amount": "100",
            "rmb_cost": "700",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert Decimal(body["xbox_account"]["local_balance"]) == Decimal("100")
    assert Decimal(body["xbox_account"]["rmb_cost"]) == Decimal("700")
    assert body["xbox_account"]["currency"] == "USD"
    assert Decimal(body["vendor_balance"]) == Decimal("700")
    assert body["xbox_transaction_id"] > 0
    assert body["vendor_transaction_id"] > 0


def test_giftcard_load_multiple_accumulate(client):
    """同账号连续加载 2 次，rmb_cost 与 local_balance 都累加"""
    vendor = _create_vendor(client, name="供B")
    xbox = _create_xbox(client, name="FREEMAN-US2", country="US")

    for face, rmb in [("50", "350"), ("80", "560")]:
        resp = client.post(
            f"/vendors/{vendor['id']}/giftcard-load",
            json={
                "xbox_account_id": xbox["id"],
                "card_face_amount": face,
                "rmb_cost": rmb,
            },
        )
        assert resp.status_code == 200, resp.text

    final = client.get("/xbox/accounts").json()
    acc = next(a for a in final if a["id"] == xbox["id"])
    assert Decimal(acc["local_balance"]) == Decimal("130")
    assert Decimal(acc["rmb_cost"]) == Decimal("910")

    txs = client.get(f"/vendors/{vendor['id']}/transactions").json()
    assert len(txs) == 2
    assert all(tx["direction"] == "in" for tx in txs)


def test_giftcard_load_vendor_not_found(client):
    xbox = _create_xbox(client, name="FREEMAN-NF")
    resp = client.post(
        "/vendors/99999/giftcard-load",
        json={"xbox_account_id": xbox["id"], "card_face_amount": "10", "rmb_cost": "70"},
    )
    assert resp.status_code == 404
    assert "供应商不存在" in resp.json()["detail"]


def test_giftcard_load_xbox_not_found(client):
    vendor = _create_vendor(client, name="供C")
    resp = client.post(
        f"/vendors/{vendor['id']}/giftcard-load",
        json={"xbox_account_id": 99999, "card_face_amount": "10", "rmb_cost": "70"},
    )
    assert resp.status_code == 404
    assert "XBOX 账号不存在" in resp.json()["detail"]


def test_giftcard_load_face_amount_zero_or_negative(client):
    vendor = _create_vendor(client, name="供D")
    xbox = _create_xbox(client, name="FREEMAN-D")

    for bad in ["0", "-5"]:
        resp = client.post(
            f"/vendors/{vendor['id']}/giftcard-load",
            json={"xbox_account_id": xbox["id"], "card_face_amount": bad, "rmb_cost": "70"},
        )
        assert resp.status_code == 400, (bad, resp.text)
        assert "卡面额" in resp.json()["detail"]


def test_giftcard_load_rmb_cost_zero_or_negative(client):
    vendor = _create_vendor(client, name="供E")
    xbox = _create_xbox(client, name="FREEMAN-E")

    for bad in ["0", "-100"]:
        resp = client.post(
            f"/vendors/{vendor['id']}/giftcard-load",
            json={"xbox_account_id": xbox["id"], "card_face_amount": "10", "rmb_cost": bad},
        )
        assert resp.status_code == 400, (bad, resp.text)
        assert "RMB 成本" in resp.json()["detail"]


def test_giftcard_load_creates_vendor_credit_transaction(client):
    """加载后查 vendor transactions 能看到该笔 credit"""
    vendor = _create_vendor(client, name="供F")
    xbox = _create_xbox(client, name="FREEMAN-F")

    resp = client.post(
        f"/vendors/{vendor['id']}/giftcard-load",
        json={"xbox_account_id": xbox["id"], "card_face_amount": "20", "rmb_cost": "140"},
    )
    assert resp.status_code == 200, resp.text

    txs = client.get(f"/vendors/{vendor['id']}/transactions").json()
    assert len(txs) == 1
    assert txs[0]["direction"] == "in"
    assert Decimal(txs[0]["amount"]) == Decimal("140")
    assert "礼品卡→XBOX" in txs[0]["remark"]


def test_giftcard_load_creates_xbox_recharge_transaction(client):
    """加载后查 XBOX transactions 能看到 type=recharge 的记录"""
    vendor = _create_vendor(client, name="供G")
    xbox = _create_xbox(client, name="FREEMAN-G")

    resp = client.post(
        f"/vendors/{vendor['id']}/giftcard-load",
        json={"xbox_account_id": xbox["id"], "card_face_amount": "30", "rmb_cost": "210"},
    )
    assert resp.status_code == 200, resp.text

    txs = client.get(f"/xbox/accounts/{xbox['id']}/transactions").json()
    assert len(txs) == 1
    assert txs[0]["type"] == "recharge"
    assert Decimal(txs[0]["rmb_amount"]) == Decimal("210")
    assert Decimal(txs[0]["local_amount"]) == Decimal("30")
    assert "礼品卡加载←供G" in txs[0]["remark"]


def test_giftcard_load_cross_country(client):
    """US (USD) 与 UK (GBP) 各加载一次，金额 / 货币正确"""
    vendor = _create_vendor(client, name="供H")
    us_xbox = _create_xbox(client, name="FREEMAN-USX", country="US")
    uk_xbox = _create_xbox(client, name="FREEMAN-UKX", country="UK")

    resp_us = client.post(
        f"/vendors/{vendor['id']}/giftcard-load",
        json={"xbox_account_id": us_xbox["id"], "card_face_amount": "100", "rmb_cost": "700"},
    )
    assert resp_us.status_code == 200, resp_us.text
    assert resp_us.json()["xbox_account"]["currency"] == "USD"
    assert Decimal(resp_us.json()["xbox_account"]["local_balance"]) == Decimal("100")

    resp_uk = client.post(
        f"/vendors/{vendor['id']}/giftcard-load",
        json={"xbox_account_id": uk_xbox["id"], "card_face_amount": "50", "rmb_cost": "500"},
    )
    assert resp_uk.status_code == 200, resp_uk.text
    assert resp_uk.json()["xbox_account"]["currency"] == "GBP"
    assert Decimal(resp_uk.json()["xbox_account"]["local_balance"]) == Decimal("50")

    # vendor 累计欠款 1200
    assert Decimal(resp_uk.json()["vendor_balance"]) == Decimal("1200")
