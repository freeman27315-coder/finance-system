import importlib
import sys

from fastapi.testclient import TestClient


def build_client(tmp_path, monkeypatch):
    monkeypatch.setenv("FINANCE_DB_PATH", str(tmp_path / "finance-test.db"))
    monkeypatch.setenv("JWT_SECRET_KEY", "test-secret")
    monkeypatch.setenv("DEFAULT_ADMIN_USERNAME", "admin")
    monkeypatch.setenv("DEFAULT_ADMIN_PASSWORD", "admin123456")
    sys.modules.pop("src.main", None)
    app_module = importlib.import_module("src.main")
    app_module.init_db()
    return TestClient(app_module.app)


def login(client, username="admin", password="admin123456"):
    response = client.post("/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def test_admin_can_create_and_list_users(tmp_path, monkeypatch):
    client = build_client(tmp_path, monkeypatch)
    admin_headers = login(client)

    response = client.post(
        "/users",
        headers=admin_headers,
        json={"username": "auditor1", "password": "password123", "role": "auditor"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["role"] == "auditor"

    response = client.get("/users", headers=admin_headers)
    assert response.status_code == 200, response.text
    assert {user["username"] for user in response.json()} >= {"admin", "auditor1"}


def test_role_permissions_for_users_and_bills(tmp_path, monkeypatch):
    client = build_client(tmp_path, monkeypatch)
    admin_headers = login(client)

    client.post(
        "/users",
        headers=admin_headers,
        json={"username": "accountant1", "password": "password123", "role": "accountant"},
    )
    client.post(
        "/users",
        headers=admin_headers,
        json={"username": "auditor1", "password": "password123", "role": "auditor"},
    )
    accountant_headers = login(client, "accountant1", "password123")
    auditor_headers = login(client, "auditor1", "password123")

    response = client.get("/users", headers=accountant_headers)
    assert response.status_code == 403

    response = client.post(
        "/bills",
        headers=accountant_headers,
        json={"amount": 128.5, "description": "Office supplies", "category": "office"},
    )
    assert response.status_code == 201, response.text

    response = client.get("/bills", headers=auditor_headers)
    assert response.status_code == 200, response.text
    assert len(response.json()) == 1

    response = client.post(
        "/bills",
        headers=auditor_headers,
        json={"amount": 1, "description": "Should fail", "category": "audit"},
    )
    assert response.status_code == 403


def test_failed_logins_lock_account(tmp_path, monkeypatch):
    client = build_client(tmp_path, monkeypatch)

    for _ in range(4):
        response = client.post("/auth/login", json={"username": "admin", "password": "bad"})
        assert response.status_code == 401

    response = client.post("/auth/login", json={"username": "admin", "password": "bad"})
    assert response.status_code == 403

    response = client.post("/auth/login", json={"username": "admin", "password": "admin123456"})
    assert response.status_code == 403


def test_refresh_and_logout(tmp_path, monkeypatch):
    client = build_client(tmp_path, monkeypatch)
    headers = login(client)

    response = client.get("/auth/me", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["username"] == "admin"

    response = client.post("/auth/refresh", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["expires_in"] == 28800

    response = client.post("/auth/logout", headers=headers)
    assert response.status_code == 200, response.text

    response = client.get("/auth/me", headers=headers)
    assert response.status_code == 401
