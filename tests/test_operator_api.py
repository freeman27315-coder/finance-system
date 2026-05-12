"""客服认证 + 账号领取 API 测试（CEO 2026-05-11）。"""
from __future__ import annotations

import pyotp
import pytest
from fastapi.testclient import TestClient

from src import database
from src.main import app
from src.services.assets import ensure_default_asset_wallets


@pytest.fixture()
def client(tmp_path):
    database.configure_database(f"sqlite:///{tmp_path / 'operator.db'}")
    database.init_db()
    db = database.SessionLocal()
    try:
        ensure_default_asset_wallets(db)
        db.commit()
    finally:
        db.close()
    return TestClient(app)


def _create_operator(client, login_name="张三", display_name="张三", password="Pwd123456"):
    r = client.post("/operator/operators", json={
        "loginName": login_name,
        "displayName": display_name,
        "password": password,
    })
    assert r.status_code == 201, r.text
    return r.json()


def _confirm_totp(client, operator_id, totp_secret):
    code = pyotp.TOTP(totp_secret).now()
    r = client.post(f"/operator/operators/{operator_id}/confirm-totp", json={"code": code})
    assert r.status_code == 200, r.text


def _create_xbox_account(client, account_no="X-001"):
    r = client.post("/xbox/accounts", json={
        "name": account_no, "country": "US", "accountNo": account_no,
        "loginEmail": "x@test.com", "password": "AcctPwd123",
    })
    assert r.status_code == 201, r.text
    return r.json()


def _mark_available(client, account_id, available=True):
    r = client.patch(f"/xbox/accounts/{account_id}/availability", json={
        "isAvailableForClaim": available
    })
    assert r.status_code == 200, r.text
    return r.json()


# ---------------- 客服注册 + TOTP ----------------


def test_create_operator_returns_totp_qr(client):
    body = _create_operator(client)
    assert body["operatorId"] >= 1
    assert len(body["totpSecret"]) >= 16
    assert body["totpUri"].startswith("otpauth://totp/")
    assert body["totpQrPngBase64"]


def test_duplicate_login_name_400(client):
    _create_operator(client, "dup_test", "dup1", "Pwd123456")
    r = client.post("/operator/operators", json={
        "loginName": "dup_test", "displayName": "x", "password": "Pwd123456",
    })
    assert r.status_code == 400
    assert "已存在" in r.json()["detail"]


def test_confirm_totp_works(client):
    body = _create_operator(client)
    _confirm_totp(client, body["operatorId"], body["totpSecret"])
    op = client.get("/operator/operators").json()[0]
    assert op["totpConfirmed"] is True


def test_confirm_totp_wrong_code_400(client):
    body = _create_operator(client)
    r = client.post(f"/operator/operators/{body['operatorId']}/confirm-totp", json={
        "code": "000000"
    })
    assert r.status_code == 400


# ---------------- 客服登录 ----------------


def test_login_requires_all_three_factors(client):
    body = _create_operator(client, "login_test", "测试", "Pwd123456")
    _confirm_totp(client, body["operatorId"], body["totpSecret"])

    # 完整登录成功
    code = pyotp.TOTP(body["totpSecret"]).now()
    r = client.post("/operator/login", json={
        "loginName": "login_test", "password": "Pwd123456", "totpCode": code,
    })
    assert r.status_code == 200, r.text
    assert "token" in r.json()
    assert r.json()["operator"]["displayName"] == "测试"


def test_login_wrong_password_401(client):
    body = _create_operator(client, "login_test_2")
    _confirm_totp(client, body["operatorId"], body["totpSecret"])
    code = pyotp.TOTP(body["totpSecret"]).now()
    r = client.post("/operator/login", json={
        "loginName": "login_test_2", "password": "wrong", "totpCode": code,
    })
    assert r.status_code == 401


def test_login_wrong_totp_401(client):
    body = _create_operator(client, "login_test_3")
    _confirm_totp(client, body["operatorId"], body["totpSecret"])
    r = client.post("/operator/login", json={
        "loginName": "login_test_3", "password": "Pwd123456", "totpCode": "000000",
    })
    assert r.status_code == 401


def test_login_before_totp_confirmed_401(client):
    body = _create_operator(client, "no_totp")
    # 没 confirm
    code = pyotp.TOTP(body["totpSecret"]).now()
    r = client.post("/operator/login", json={
        "loginName": "no_totp", "password": "Pwd123456", "totpCode": code,
    })
    assert r.status_code == 401


# ---------------- 账号"可出库" ----------------


def test_mark_account_available_for_claim(client):
    account = _create_xbox_account(client)
    assert account["isAvailableForClaim"] is False  # 默认 false

    updated = _mark_available(client, account["id"], True)
    assert updated["isAvailableForClaim"] is True

    # 再标 false
    updated = _mark_available(client, account["id"], False)
    assert updated["isAvailableForClaim"] is False


# ---------------- 账号领取 ----------------


def test_claim_account_happy_path(client):
    op = _create_operator(client, "claimer")
    account = _create_xbox_account(client, "CLAIM-1")
    _mark_available(client, account["id"], True)

    # 领取
    r = client.post("/operator/claims", json={
        "accountId": account["id"], "operatorId": op["operatorId"]
    })
    assert r.status_code == 201, r.text
    claim = r.json()
    assert claim["isActive"] is True

    # 出现在 my claims
    my = client.get(f"/operator/operators/{op['operatorId']}/claims").json()
    assert len(my) == 1


def test_claim_account_not_available_400(client):
    op = _create_operator(client, "no_available")
    account = _create_xbox_account(client, "NOAVAIL-1")
    # 没标可出库

    r = client.post("/operator/claims", json={
        "accountId": account["id"], "operatorId": op["operatorId"]
    })
    assert r.status_code == 400
    assert "可出库" in r.json()["detail"]


def test_claim_account_already_claimed_by_other_400(client):
    op_a = _create_operator(client, "op_a")
    op_b = _create_operator(client, "op_b")
    account = _create_xbox_account(client, "DUAL-1")
    _mark_available(client, account["id"], True)

    # op_a 先领
    client.post("/operator/claims", json={
        "accountId": account["id"], "operatorId": op_a["operatorId"]
    })
    # op_b 想领,失败
    r = client.post("/operator/claims", json={
        "accountId": account["id"], "operatorId": op_b["operatorId"]
    })
    assert r.status_code == 400
    assert "已被" in r.json()["detail"]


def test_claim_max_3_per_operator(client):
    op = _create_operator(client, "max_3")
    accounts = [_create_xbox_account(client, f"MAX-{i}") for i in range(4)]
    for a in accounts:
        _mark_available(client, a["id"], True)

    # 领 3 个 OK
    for i in range(3):
        r = client.post("/operator/claims", json={
            "accountId": accounts[i]["id"], "operatorId": op["operatorId"]
        })
        assert r.status_code == 201

    # 第 4 个失败
    r = client.post("/operator/claims", json={
        "accountId": accounts[3]["id"], "operatorId": op["operatorId"]
    })
    assert r.status_code == 400
    assert "上限" in r.json()["detail"]


def test_return_claim_releases_account(client):
    op = _create_operator(client, "returner")
    account = _create_xbox_account(client, "RET-1")
    _mark_available(client, account["id"], True)

    r = client.post("/operator/claims", json={
        "accountId": account["id"], "operatorId": op["operatorId"]
    })
    claim_id = r.json()["id"]

    # 归还
    r = client.post(f"/operator/claims/{claim_id}/return", json={
        "operatorId": op["operatorId"]
    })
    assert r.status_code == 200
    assert r.json()["isActive"] is False
    assert r.json()["returnReason"] == "manual"

    # 再领同账号 OK
    r = client.post("/operator/claims", json={
        "accountId": account["id"], "operatorId": op["operatorId"]
    })
    assert r.status_code == 201


def test_force_recall_by_admin(client):
    """CEO 后台强制回收(不需要是持有人)。"""
    op = _create_operator(client, "victim")
    account = _create_xbox_account(client, "RECALL-1")
    _mark_available(client, account["id"], True)
    r = client.post("/operator/claims", json={
        "accountId": account["id"], "operatorId": op["operatorId"]
    })
    claim_id = r.json()["id"]

    # 没传 operator_id,但 force_recall=true
    r = client.post(f"/operator/claims/{claim_id}/return", json={
        "forceRecall": True
    })
    assert r.status_code == 200
    assert r.json()["isActive"] is False
    assert r.json()["returnReason"] == "force_recall_by_admin"


def test_available_accounts_excludes_claimed(client):
    op = _create_operator(client, "avail_test")
    a1 = _create_xbox_account(client, "AV-1")
    a2 = _create_xbox_account(client, "AV-2")
    _mark_available(client, a1["id"], True)
    _mark_available(client, a2["id"], True)

    # 都可出库 → 都在 available 列表
    avail = client.get("/operator/available-accounts").json()
    assert {a["id"] for a in avail} >= {a1["id"], a2["id"]}

    # 领 a1 → 应该只剩 a2 可出库
    client.post("/operator/claims", json={
        "accountId": a1["id"], "operatorId": op["operatorId"]
    })
    avail = client.get("/operator/available-accounts").json()
    ids = {a["id"] for a in avail}
    assert a1["id"] not in ids
    assert a2["id"] in ids
