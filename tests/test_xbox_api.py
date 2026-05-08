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
    # 改为 camelCase（PR #103 统一 alias）
    assert Decimal(refreshed["rmbCost"]) == Decimal("700.000000")
    assert Decimal(refreshed["localBalance"]) == Decimal("64.500000")


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


# ---------------------------------------------------------------------------
# PR #103 (issue #102) - 账号库存升级测试
# ---------------------------------------------------------------------------


def test_create_account_with_new_fields(client):
    """新增账号支持 account_no / login_email / password / exchange_rate / status。"""
    response = client.post(
        "/xbox/accounts",
        json={
            "name": "丙火 US 主号",
            "country": "US",
            "accountNo": "BH-US-001",
            "loginEmail": "user1@outlook.com",
            "password": "MySecret123!",
            "exchangeRate": "7.20",
            "status": "active",
            "remark": "主账号",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["accountNo"] == "BH-US-001"
    assert body["loginEmail"] == "user1@outlook.com"
    assert body["hasPassword"] is True
    # 关键：明文密码不能出现在响应里
    assert "password" not in body
    assert "passwordEnc" not in body
    assert body["status"] == "active"
    assert Decimal(body["exchangeRate"]) == Decimal("7.20")


def test_create_account_duplicate_account_no_400(client):
    """同 account_no 重复 → 400。"""
    client.post(
        "/xbox/accounts",
        json={"name": "A1", "country": "US", "accountNo": "DUP-001"},
    )
    r2 = client.post(
        "/xbox/accounts",
        json={"name": "A2", "country": "US", "accountNo": "DUP-001"},
    )
    assert r2.status_code == 400
    assert "已存在" in r2.json()["detail"]


def test_patch_account_updates_normal_fields_writes_audit(client):
    """改普通字段 → 字段更新 + 审计日志记录。"""
    body = create_account(client, "原名", "US")
    aid = body["id"]

    r = client.patch(
        f"/xbox/accounts/{aid}",
        json={"name": "新名", "loginEmail": "new@x.com", "exchangeRate": "7.15"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "新名"
    assert r.json()["loginEmail"] == "new@x.com"
    assert Decimal(r.json()["exchangeRate"]) == Decimal("7.15")

    logs = client.get(f"/xbox/accounts/{aid}/audit-logs").json()
    assert any(log["action"] == "created" for log in logs)
    assert any(log["action"] == "updated" for log in logs)


def test_patch_password_and_status_audited_separately(client):
    """改密码 / 改状态走单独端点,各写一条审计。"""
    body = create_account(client, "测试号", "US")
    aid = body["id"]

    # 改密码
    r = client.patch(f"/xbox/accounts/{aid}/password", json={"password": "NewPwd456"})
    assert r.status_code == 200
    assert r.json()["hasPassword"] is True

    # 改状态
    r = client.patch(
        f"/xbox/accounts/{aid}/status",
        json={"status": "error", "statusMessage": "登录失败"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "error"
    assert r.json()["statusMessage"] == "登录失败"

    logs = client.get(f"/xbox/accounts/{aid}/audit-logs").json()
    actions = [log["action"] for log in logs]
    assert "password_changed" in actions
    assert "status_changed" in actions


def test_password_encrypt_decrypt_roundtrip():
    """加密再解密回明文（直接调 service 验证）。"""
    from src.utils.crypto import decrypt_password, encrypt_password

    plain = "Hello世界123!"
    enc = encrypt_password(plain)
    assert enc != plain  # 必须加密后不同
    assert decrypt_password(enc) == plain


def test_password_decrypt_with_wrong_data_raises():
    """密文被篡改 → 解密失败。"""
    from src.utils.crypto import CryptoError, encrypt_password, decrypt_password

    enc = encrypt_password("orig")
    # 改一位
    bad = enc[:-2] + ("AA" if enc[-2:] != "AA" else "BB")
    with pytest.raises(CryptoError):
        decrypt_password(bad)


def test_list_accounts_filter_by_status(client):
    """按 status 过滤列表。"""
    create_account(client, "A1", "US")
    body = create_account(client, "A2", "US")
    client.patch(f"/xbox/accounts/{body['id']}/status", json={"status": "disabled"})

    r = client.get("/xbox/accounts", params={"status": "active"})
    assert r.status_code == 200
    names = [a["name"] for a in r.json()]
    assert "A1" in names
    assert "A2" not in names


def test_status_filter_returns_disabled(client):
    """status=disabled 只返回停用账号。"""
    body = create_account(client, "A1", "US")
    client.patch(f"/xbox/accounts/{body['id']}/status", json={"status": "disabled"})

    r = client.get("/xbox/accounts", params={"status": "disabled"})
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["status"] == "disabled"


def test_existing_xbox_data_compatible(client):
    """老接口（仅 name + country）仍能创建账号,不填新字段不报错。"""
    body = create_account(client, "兼容老逻辑", "US")
    assert body["status"] == "active"
    assert body["hasPassword"] is False
    assert body["accountNo"] is None
    assert body["loginEmail"] is None


def test_patch_account_can_change_account_no(client):
    """编辑接口支持改 account_no,会同步 name + 写审计。"""
    body = client.post(
        "/xbox/accounts",
        json={"name": "TMP", "country": "US", "accountNo": "OLD-001"},
    ).json()
    aid = body["id"]

    r = client.patch(f"/xbox/accounts/{aid}", json={"accountNo": "NEW-002"})
    assert r.status_code == 200, r.text
    assert r.json()["accountNo"] == "NEW-002"
    # name 也应同步成新 account_no(前端用 account_no 作主标识)
    assert r.json()["name"] == "NEW-002"

    logs = client.get(f"/xbox/accounts/{aid}/audit-logs").json()
    detail = next(l["detail"] for l in logs if l["action"] == "updated")
    assert "account_no" in detail
    assert "OLD-001" in detail
    assert "NEW-002" in detail


def test_patch_account_no_conflict_returns_400(client):
    """改 account_no 时新编号已被占用 → 400。"""
    client.post(
        "/xbox/accounts",
        json={"name": "A1", "country": "US", "accountNo": "TAKEN"},
    )
    body2 = client.post(
        "/xbox/accounts",
        json={"name": "A2", "country": "US", "accountNo": "FREE"},
    ).json()

    r = client.patch(f"/xbox/accounts/{body2['id']}", json={"accountNo": "TAKEN"})
    assert r.status_code == 400
    assert "已被其他账号占用" in r.json()["detail"]
