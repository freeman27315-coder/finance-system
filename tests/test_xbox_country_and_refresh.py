"""自动识别国家 + 刷新余额 API (CEO 2026-05-12)。"""
from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from src import database
from src.main import app
from src.services.assets import ensure_default_asset_wallets


@pytest.fixture()
def client(tmp_path):
    database.configure_database(f"sqlite:///{tmp_path / 'xbox_country.db'}")
    database.init_db()
    db = database.SessionLocal()
    try:
        ensure_default_asset_wallets(db)
        db.commit()
    finally:
        db.close()
    return TestClient(app)


def _create_account(client, account_no: str, country: str | None = None, password: str | None = "MSPwd123"):
    payload = {
        "name": account_no,
        "accountNo": account_no,
        "loginEmail": f"{account_no.lower()}@test.com",
    }
    if country is not None:
        payload["country"] = country
    if password is not None:
        payload["password"] = password
    r = client.post("/xbox/accounts", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


# ------------- 国家自动识别 -------------


def test_account_without_country_starts_unidentified(client):
    """CEO 2026-05-12 Q1-A: 创建账号不传 country → 占位 US + country_identified=False。"""
    acc = _create_account(client, "AUTO-1", country=None)
    # 占位是 US (但 country_identified=False 标记为"待识别")
    assert acc["country"] == "US"
    assert acc["countryIdentified"] is False


def test_account_with_explicit_country_is_marked_identified(client):
    """CEO 兜底: 如果 CEO 明确传 country, 视为已识别(skip auto-detect)。"""
    acc = _create_account(client, "MANUAL-UK", country="UK")
    assert acc["country"] == "UK"
    assert acc["countryIdentified"] is True


def test_sync_auto_identifies_country_from_balance_currency(client):
    """同步抓到 currency 后,自动更新 country/currency + 标 identified。

    mock stub 用 account.country 决定 stub currency, 所以会和占位一致(US/USD)。
    但 country_identified 应该从 False 变 True。
    """
    acc = _create_account(client, "AUTO-2", country=None)
    assert acc["countryIdentified"] is False

    r = client.post("/xbox/sync/orders", json={"accountId": acc["id"], "count": 10})
    assert r.status_code == 200, r.text
    assert r.json()["success"] is True

    after = client.get("/xbox/accounts").json()
    a = next(x for x in after if x["id"] == acc["id"])
    assert a["countryIdentified"] is True
    # currency 与 country 一致(US→USD)
    assert (a["country"], a["currency"]) in [("US", "USD"), ("UK", "GBP")]


# ------------- 单账号刷新余额 -------------


def test_refresh_balance_updates_balance_and_country(client):
    """CEO 2026-05-12 Q2: 单账号刷新按钮 → 更新余额 + 识别国家(不写订单)。"""
    acc = _create_account(client, "REFRESH-1", country=None)
    assert Decimal(acc["localBalance"]) == Decimal("0")
    assert acc["countryIdentified"] is False

    r = client.post(f"/xbox/accounts/{acc['id']}/refresh-balance")
    assert r.status_code == 200, r.text
    body = r.json()
    # mock stub 给的余额 = 123.45 + id*10
    assert Decimal(body["localBalance"]) > Decimal("0")
    assert body["countryIdentified"] is True
    assert body["lastSyncedAt"] is not None

    # 没有订单被写入(因为只刷余额)
    orders = client.get(f"/xbox/orders?accountId={acc['id']}").json()
    assert len(orders) == 0


def test_refresh_balance_without_credentials_keeps_balance(client):
    """账号没设密码 → 刷新失败,但端点返回 200(让 CEO 看到状态),余额不变。"""
    acc = _create_account(client, "NO-CRED", country=None, password=None)

    r = client.post(f"/xbox/accounts/{acc['id']}/refresh-balance")
    assert r.status_code == 200
    body = r.json()
    # 余额仍为 0(没刷成功)
    assert Decimal(body["localBalance"]) == Decimal("0")
    # 国家也没识别
    assert body["countryIdentified"] is False


# ------------- 全部刷新 -------------


def test_refresh_all_balances_returns_summary(client):
    """CEO 2026-05-12 Q2: 总刷新按钮 → 串行刷所有 active 账号 + 返回摘要。"""
    _create_account(client, "ALL-1", country=None)
    _create_account(client, "ALL-2", country=None)
    _create_account(client, "ALL-3", country=None)
    # 一个没密码 → 刷新失败
    _create_account(client, "ALL-FAIL", country=None, password=None)

    r = client.post("/xbox/refresh-all-balances")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 4
    assert body["succeeded"] == 3
    assert body["failed"] == 1
    assert len(body["accounts"]) == 4
    # 成功的 3 个都已识别国家
    succeeded_accounts = [a for a in body["accounts"] if a["countryIdentified"]]
    assert len(succeeded_accounts) == 3
