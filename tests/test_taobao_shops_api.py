from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from src import database
from src.main import app
from src.models.taobao import TaobaoShop
from src.models.wallet import Currency, Wallet, WalletType
from src.services.assets import ensure_default_asset_wallets
from src.services.taobao import ensure_default_taobao_wallets


@pytest.fixture()
def client(tmp_path):
    database.configure_database(f"sqlite:///{tmp_path / 'taobao.db'}")
    database.init_db()
    db = database.SessionLocal()
    try:
        ensure_default_asset_wallets(db)
        ensure_default_taobao_wallets(db)
        db.commit()
    finally:
        db.close()
    return TestClient(app)


def test_get_shops_returns_three_shops_with_six_wallets(client):
    response = client.get("/taobao/shops")
    assert response.status_code == 200, response.text
    shops = response.json()

    assert len(shops) == 3
    assert {shop["name"] for shop in shops} == {"丙火电玩", "兔仔电玩", "小小电玩"}

    for shop in shops:
        assert "unconfirmedAlipay" in shop
        assert "unconfirmedWechat" in shop
        assert "aggregatorFrozen" in shop
        assert "aggregatorAvailable" in shop
        assert "bankCard" in shop
        assert "paymentWallet" in shop  # may be null for 兔仔
        assert "createdAt" in shop
        # 5 个内部钱包都应该带 id / name / balance
        for key in ("unconfirmedAlipay", "unconfirmedWechat", "aggregatorFrozen", "aggregatorAvailable", "bankCard"):
            assert shop[key]["id"]
            assert shop[key]["name"]
            assert Decimal(shop[key]["balance"]) == Decimal("0.000000")


def test_payment_wallet_mapping(client):
    response = client.get("/taobao/shops")
    shops = {shop["name"]: shop for shop in response.json()}

    binghuo = shops["丙火电玩"]
    assert binghuo["paymentWallet"] is not None
    assert binghuo["paymentWallet"]["name"] == "丙火网络支付宝"

    tuzai = shops["兔仔电玩"]
    assert tuzai["paymentWallet"] is None

    xiaoxiao = shops["小小电玩"]
    assert xiaoxiao["paymentWallet"] is not None
    assert xiaoxiao["paymentWallet"]["name"] == "小小电玩支付宝"


def test_each_shop_has_five_taobao_wallets_in_db(client, tmp_path):
    db = database.SessionLocal()
    try:
        shops = db.scalars(select(TaobaoShop)).all()
        assert len(shops) == 3
        for shop in shops:
            taobao_wallets = db.scalars(
                select(Wallet).where(
                    Wallet.parent_id.is_(None),
                    Wallet.type == WalletType.TAOBAO.value,
                    Wallet.name.like(f"{shop.name}%"),
                )
            ).all()
            assert len(taobao_wallets) == 5
            assert {w.currency for w in taobao_wallets} == {Currency.CNY.value}
    finally:
        db.close()


def test_ensure_default_taobao_wallets_is_idempotent(client):
    db = database.SessionLocal()
    try:
        before_shops = db.scalar(
            select(Wallet).where(Wallet.type == WalletType.TAOBAO.value)
        )
        before_taobao_count = len(
            db.scalars(select(Wallet).where(Wallet.type == WalletType.TAOBAO.value)).all()
        )
        before_shop_count = len(db.scalars(select(TaobaoShop)).all())

        # 第二次调用，应不重复创建
        ensure_default_taobao_wallets(db)
        db.commit()

        after_taobao_count = len(
            db.scalars(select(Wallet).where(Wallet.type == WalletType.TAOBAO.value)).all()
        )
        after_shop_count = len(db.scalars(select(TaobaoShop)).all())

        assert before_taobao_count == after_taobao_count == 15  # 3 shops * 5 wallets
        assert before_shop_count == after_shop_count == 3
    finally:
        db.close()


def test_xiaoxiao_alipay_visible_in_asset_list(client):
    response = client.get("/wallets/assets")
    assert response.status_code == 200, response.text
    assets = response.json()

    # 找到支付宝钱包分组并检查其下含小小电玩支付宝
    rmb_root = next(w for w in assets if w["name"] == "RMB钱包")
    alipay_group = next(c for c in rmb_root["children"] if c["name"] == "支付宝钱包")
    sub_names = {child["name"] for child in alipay_group["children"]}
    assert "小小电玩支付宝" in sub_names
    assert "丙火网络支付宝" in sub_names
