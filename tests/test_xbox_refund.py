"""XBOX 退款单测试 (Issue #130 / CEO 2026-05-18)。

覆盖:
- 正向: 创建退款 → sale_record 标 refunded、实际钱包 + 理论钱包都减钱
- 重复退款拒绝
- 销售记录不存在 → 404
- 撤销: 状态回到 active、钱回来
- 对账 OUT 方向: 退款当日 theoreticalOutTotal / actualOutTotal / outDiff 显示
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from src import database
from src.main import app
from src.models.wallet import Wallet
from src.models.xbox import XboxRefund, XboxSaleRecord
from src.services.assets import ensure_default_asset_wallets
from src.services.taiwan import ensure_default_taiwan_wallets
from src.services.taobao import (
    ensure_default_taobao_wallets,
    ensure_shop_total_group_wallets,
)
from src.services.xbox_sales_ledger import (
    ensure_xbox_default_reconcile_mappings,
    ensure_xbox_default_wallet_settings,
    ensure_xbox_sales_ledger_wallets,
)


@pytest.fixture()
def client(tmp_path):
    database.configure_database(f"sqlite:///{tmp_path / 'xbox_refund.db'}")
    database.init_db()
    db = database.SessionLocal()
    try:
        ensure_default_asset_wallets(db)
        ensure_default_taobao_wallets(db)
        ensure_default_taiwan_wallets(db)
        leaf_id_by_name = ensure_xbox_sales_ledger_wallets(db)
        ensure_xbox_default_wallet_settings(db, leaf_id_by_name)
        ensure_shop_total_group_wallets(db)
        ensure_xbox_default_reconcile_mappings(db)
        db.commit()
    finally:
        db.close()
    return TestClient(app)


# -------- helpers --------


def _get_wallet_id_by_name(name: str) -> int:
    db = database.SessionLocal()
    try:
        wallet = db.scalar(select(Wallet).where(Wallet.name == name, Wallet.deleted_at.is_(None)))
        if wallet is None:
            raise AssertionError(f"未找到钱包 {name}")
        return wallet.id
    finally:
        db.close()


def _wallet_balance(wallet_id: int) -> Decimal:
    db = database.SessionLocal()
    try:
        w = db.get(Wallet, wallet_id)
        return Decimal(w.balance)
    finally:
        db.close()


def _create_account(client, account_no="REFUND-001"):
    r = client.post(
        "/xbox/accounts",
        json={
            "name": account_no,
            "country": "US",
            "accountNo": account_no,
            "exchangeRate": "7.20",
            "loginEmail": f"{account_no}@test.com",
            "password": "TestPwd123",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def _push_wallet_settings(client, items: list[dict]):
    r = client.put(
        "/xbox/wallet-settings",
        json=[{"code": "agent", "label": "代理", "items": items}],
    )
    assert r.status_code == 200, r.text
    return r.json()


def _seed_sale_record(client, sale_price="800.00", account_no="REFUND-001") -> dict:
    """建一笔销售记录: 走"建订单 → 补齐字段自动转销售"流程.

    返回 sale_record 字典 (含 id / pool_id / actual_wallet_id).
    """
    # 用"丙火网络"理论钱包 + "丙火网络支付宝"实际(CNY)做对子, 已自动映射
    pool_id = _get_wallet_id_by_name("丙火网络")  # 理论钱包(XBOX_SALES_LEDGER, CNY)
    actual_id = _get_wallet_id_by_name("丙火网络支付宝")  # 实际钱包(ASSET_RMB)

    _push_wallet_settings(
        client,
        [{"code": "001", "label": "代理 001", "walletPoolId": pool_id}],
    )
    method_id = client.get("/xbox/wallet-settings").json()[0]["id"]
    item_id = client.get("/xbox/wallet-settings").json()[0]["items"][0]["id"]

    account = _create_account(client, account_no=account_no)
    # 用唯一的 orderNo (account_no 嵌进去防同测试多个销售时重复)
    order_no = f"ORD-{account_no}"
    order = client.post(
        "/xbox/orders",
        json={
            "accountId": account["id"],
            "orderNo": order_no,
            "amountLocal": "100",
            "currencyLocal": "USD",
            "orderAt": "2026-05-18T10:00:00",
        },
    ).json()
    r = client.patch(
        f"/xbox/orders/{order['id']}",
        json={
            "saleDate": "2026-05-18",
            "productName": "Game A",
            "operatorName": "运营 A",
            "salePrice": sale_price,
            "saleCurrency": "CNY",
            "walletMethodId": method_id,
            "walletItemId": item_id,
        },
    )
    assert r.status_code == 200, r.text
    sale_record_id = r.json()["saleRecordId"]
    return {
        "sale_record_id": sale_record_id,
        "pool_id": pool_id,  # 理论钱包
        "actual_id": actual_id,  # 实际钱包
        "sale_price": Decimal(sale_price),
    }


# ===================================================================
# 1. 创建退款 → 销售记录标 refunded, 两个钱包都减钱
# ===================================================================


def test_create_refund_marks_sale_record_and_debits_both_wallets(client):
    seed = _seed_sale_record(client)
    pool_id = seed["pool_id"]
    actual_id = seed["actual_id"]

    # 销售时 credit 800 到理论钱包(资金池), 实际钱包没动
    assert _wallet_balance(pool_id) == Decimal("800.000000")
    assert _wallet_balance(actual_id) == Decimal("0")

    # 先给实际钱包充钱(模拟客户已经付过钱进来了)
    r = client.post(f"/wallets/assets/{actual_id}/credit", json={"amount": "800"})
    assert r.status_code == 201, r.text
    assert _wallet_balance(actual_id) == Decimal("800.000000")

    # 发起退款
    r = client.post(
        "/api/xbox/refunds",
        json={
            "sale_record_id": seed["sale_record_id"],
            "actual_wallet_id": actual_id,
            "business_date": "2026-05-18",
            "operator_name": "freeman",
            "note": "没充上, 全额退",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert Decimal(body["refund_amount"]) == Decimal("800")
    assert body["refund_currency"] == "CNY"
    assert body["actual_wallet_id"] == actual_id
    assert body["theoretical_wallet_id"] == pool_id
    assert body["operator_name"] == "freeman"
    assert body["sale_record"]["id"] == seed["sale_record_id"]
    # 两条流水 id 都被记下来了
    assert body["actual_bookkeeping_tx_id"] is not None
    assert body["theoretical_bookkeeping_tx_id"] is not None

    # 实际钱包 800 → 0
    assert _wallet_balance(actual_id) == Decimal("0")
    # 理论钱包 800 → 0 (销售时 +800, 退款 -800)
    assert _wallet_balance(pool_id) == Decimal("0")

    # 销售记录已标 refunded
    db = database.SessionLocal()
    try:
        record = db.get(XboxSaleRecord, seed["sale_record_id"])
        assert record.status == "refunded"
        assert record.refunded_at is not None
        assert record.refund_id == body["id"]
    finally:
        db.close()


# ===================================================================
# 2. 重复退款 → 400
# ===================================================================


def test_refund_twice_is_rejected(client):
    seed = _seed_sale_record(client)
    actual_id = seed["actual_id"]
    client.post(f"/wallets/assets/{actual_id}/credit", json={"amount": "800"})

    # 第一次退款 OK
    r1 = client.post(
        "/api/xbox/refunds",
        json={"sale_record_id": seed["sale_record_id"], "actual_wallet_id": actual_id},
    )
    assert r1.status_code == 201

    # 第二次失败 (sale_record.status='refunded')
    r2 = client.post(
        "/api/xbox/refunds",
        json={"sale_record_id": seed["sale_record_id"], "actual_wallet_id": actual_id},
    )
    assert r2.status_code == 400, r2.text
    assert "不能退款" in r2.json()["detail"]


# ===================================================================
# 3. 销售记录不存在 → 404
# ===================================================================


def test_refund_nonexistent_sale_record_returns_404(client):
    actual_id = _get_wallet_id_by_name("丙火网络支付宝")
    r = client.post(
        "/api/xbox/refunds",
        json={"sale_record_id": 99999, "actual_wallet_id": actual_id},
    )
    assert r.status_code == 404, r.text
    assert "不存在" in r.json()["detail"]


# ===================================================================
# 4. 实际钱包不存在 / 非法 → 404 或 400
# ===================================================================


def test_refund_nonexistent_actual_wallet_returns_404(client):
    seed = _seed_sale_record(client)
    r = client.post(
        "/api/xbox/refunds",
        json={"sale_record_id": seed["sale_record_id"], "actual_wallet_id": 99999},
    )
    assert r.status_code == 404, r.text


def test_refund_to_group_wallet_returns_400(client):
    """实际钱包是 group 节点 → 400 拒绝."""
    seed = _seed_sale_record(client)
    # 找一个 group 钱包 (淘宝店铺总钱包是 group)
    db = database.SessionLocal()
    try:
        group = db.scalar(
            select(Wallet).where(Wallet.is_group.is_(True), Wallet.deleted_at.is_(None))
        )
        group_id = group.id if group else None
    finally:
        db.close()
    if group_id is None:
        pytest.skip("没有 group 钱包可测")

    r = client.post(
        "/api/xbox/refunds",
        json={"sale_record_id": seed["sale_record_id"], "actual_wallet_id": group_id},
    )
    assert r.status_code == 400, r.text
    assert "分组" in r.json()["detail"]


# ===================================================================
# 5. 撤销退款: 状态回到 active, 钱回来
# ===================================================================


def test_cancel_refund_restores_state(client):
    seed = _seed_sale_record(client)
    actual_id = seed["actual_id"]
    pool_id = seed["pool_id"]
    client.post(f"/wallets/assets/{actual_id}/credit", json={"amount": "800"})

    # 退款
    r = client.post(
        "/api/xbox/refunds",
        json={"sale_record_id": seed["sale_record_id"], "actual_wallet_id": actual_id},
    )
    assert r.status_code == 201
    refund_id = r.json()["id"]

    assert _wallet_balance(actual_id) == Decimal("0")
    assert _wallet_balance(pool_id) == Decimal("0")

    # 撤销
    r = client.delete(f"/api/xbox/refunds/{refund_id}")
    assert r.status_code == 200, r.text
    assert r.json()["cancelled_refund_id"] == refund_id

    # 钱回来
    assert _wallet_balance(actual_id) == Decimal("800.000000")
    assert _wallet_balance(pool_id) == Decimal("800.000000")

    # 销售记录回到 active
    db = database.SessionLocal()
    try:
        record = db.get(XboxSaleRecord, seed["sale_record_id"])
        assert record.status == "active"
        assert record.refunded_at is None
        assert record.refund_id is None
        # 退款单已硬删
        assert db.get(XboxRefund, refund_id) is None
    finally:
        db.close()


# ===================================================================
# 6. 撤销后, 可以再次创建退款 (UNIQUE 约束不阻塞二次退款)
# ===================================================================


def test_can_create_refund_again_after_cancel(client):
    seed = _seed_sale_record(client)
    actual_id = seed["actual_id"]
    client.post(f"/wallets/assets/{actual_id}/credit", json={"amount": "800"})

    r1 = client.post(
        "/api/xbox/refunds",
        json={"sale_record_id": seed["sale_record_id"], "actual_wallet_id": actual_id},
    )
    assert r1.status_code == 201
    refund_id = r1.json()["id"]
    client.delete(f"/api/xbox/refunds/{refund_id}")

    # 再退款 OK (钱回来后再退). 不校验 id 不同 — SQLite 可能复用删掉的 id,
    # 重点是 201 + 销售记录再次进 refunded 状态.
    r2 = client.post(
        "/api/xbox/refunds",
        json={"sale_record_id": seed["sale_record_id"], "actual_wallet_id": actual_id},
    )
    assert r2.status_code == 201, r2.text
    new_refund_id = r2.json()["id"]
    # 销售记录已重新进 refunded
    db = database.SessionLocal()
    try:
        record = db.get(XboxSaleRecord, seed["sale_record_id"])
        assert record.status == "refunded"
        assert record.refund_id == new_refund_id
    finally:
        db.close()


# ===================================================================
# 7. 撤销不存在的退款 → 404
# ===================================================================


def test_cancel_nonexistent_refund_returns_404(client):
    r = client.delete("/api/xbox/refunds/99999")
    assert r.status_code == 404, r.text


# ===================================================================
# 8. 列表 + 筛选
# ===================================================================


def test_list_refunds_with_filters(client):
    seed = _seed_sale_record(client, account_no="REFUND-LIST")
    actual_id = seed["actual_id"]
    client.post(f"/wallets/assets/{actual_id}/credit", json={"amount": "800"})

    client.post(
        "/api/xbox/refunds",
        json={
            "sale_record_id": seed["sale_record_id"],
            "actual_wallet_id": actual_id,
            "operator_name": "freeman",
            "business_date": "2026-05-18",
        },
    )

    # 全部
    r = client.get("/api/xbox/refunds")
    assert r.status_code == 200
    items = r.json()
    assert len(items) >= 1

    # 按操作人筛
    r = client.get("/api/xbox/refunds", params={"operator_name": "freeman"})
    assert all(it["operator_name"] == "freeman" for it in r.json())

    # 按实际钱包筛
    r = client.get("/api/xbox/refunds", params={"actual_wallet_id": actual_id})
    assert all(it["actual_wallet_id"] == actual_id for it in r.json())

    # 详情
    refund_id = items[0]["id"]
    r = client.get(f"/api/xbox/refunds/{refund_id}")
    assert r.status_code == 200
    assert r.json()["id"] == refund_id


# ===================================================================
# 9. 对账 OUT 方向: 退款当日 theoreticalOutTotal / actualOutTotal / outDiff
# ===================================================================


def test_reconcile_report_includes_out_direction_for_refund_day(client):
    seed = _seed_sale_record(client, account_no="REFUND-RECON")
    actual_id = seed["actual_id"]
    pool_id = seed["pool_id"]
    client.post(f"/wallets/assets/{actual_id}/credit", json={"amount": "800"})

    # 退款 business_date = 2026-05-18
    r = client.post(
        "/api/xbox/refunds",
        json={
            "sale_record_id": seed["sale_record_id"],
            "actual_wallet_id": actual_id,
            "business_date": "2026-05-18",
        },
    )
    assert r.status_code == 201

    # 对账 2026-05-18
    r = client.get("/xbox/reconcile", params={"date": "2026-05-18"})
    assert r.status_code == 200, r.text
    rows = r.json()

    # 找到"丙火网络"理论钱包那一行
    binghuo_row = next(
        (row for row in rows if row["theoreticalWallet"]["id"] == pool_id), None
    )
    assert binghuo_row is not None

    # IN 方向 (销售): 理论 = 800 (销售记录 status=refunded 但 sale_price 还在汇总)
    assert Decimal(binghuo_row["theoreticalTotal"]) == Decimal("800")
    # OUT 方向 (退款) 应该 = 800
    assert Decimal(binghuo_row["theoreticalOutTotal"]) == Decimal("800")
    # 实际 OUT 方向 也应该 = 800 (从 actual_wallet 扣的钱)
    assert Decimal(binghuo_row["actualOutTotal"]) == Decimal("800")
    # 差异 = 0 (理论 OUT - 实际 OUT)
    assert Decimal(binghuo_row["outDiff"]) == Decimal("0")
    # 每个实际钱包子行也带 outTotal
    for sub in binghuo_row["actualWallets"]:
        if sub["id"] == actual_id:
            assert Decimal(sub["outTotal"]) == Decimal("800")


def test_reconcile_report_other_day_has_zero_out(client):
    """退款只算在 business_date 那天, 其他日期 OUT 为 0."""
    seed = _seed_sale_record(client, account_no="REFUND-OTHER-DAY")
    actual_id = seed["actual_id"]
    pool_id = seed["pool_id"]
    client.post(f"/wallets/assets/{actual_id}/credit", json={"amount": "800"})

    client.post(
        "/api/xbox/refunds",
        json={
            "sale_record_id": seed["sale_record_id"],
            "actual_wallet_id": actual_id,
            "business_date": "2026-05-18",
        },
    )

    # 查另一天 2026-05-19
    r = client.get("/xbox/reconcile", params={"date": "2026-05-19"})
    rows = r.json()
    binghuo_row = next(
        (row for row in rows if row["theoreticalWallet"]["id"] == pool_id), None
    )
    assert binghuo_row is not None
    assert Decimal(binghuo_row["theoreticalOutTotal"]) == Decimal("0")
    assert Decimal(binghuo_row["actualOutTotal"]) == Decimal("0")
    assert Decimal(binghuo_row["outDiff"]) == Decimal("0")
