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
        assert "storeAlipayWallet" in shop  # 每店铺都有,不再可空
        assert shop["storeAlipayWallet"] is not None
        assert "createdAt" in shop
        # 5 个内部钱包 + 店铺支付宝都应该带 id / name / balance / type
        for key in (
            "unconfirmedAlipay",
            "unconfirmedWechat",
            "aggregatorFrozen",
            "aggregatorAvailable",
            "bankCard",
            "storeAlipayWallet",
        ):
            assert shop[key]["id"]
            assert shop[key]["name"]
            assert "type" in shop[key]
            assert Decimal(shop[key]["balance"]) == Decimal("0.000000")


def test_store_alipay_wallet_mapping(client):
    response = client.get("/taobao/shops")
    shops = {shop["name"]: shop for shop in response.json()}

    # 丙火/小小指向资产支付宝下的子钱包（type=asset_rmb）
    binghuo = shops["丙火电玩"]
    assert binghuo["storeAlipayWallet"]["name"] == "丙火网络支付宝"
    assert binghuo["storeAlipayWallet"]["type"] == WalletType.ASSET_RMB.value

    xiaoxiao = shops["小小电玩"]
    assert xiaoxiao["storeAlipayWallet"]["name"] == "小小电玩支付宝"
    assert xiaoxiao["storeAlipayWallet"]["type"] == WalletType.ASSET_RMB.value

    # 兔仔指向独立的 type=TAOBAO 顶级钱包"兔仔电玩支付宝"（账面记账,不在资产页）
    tuzai = shops["兔仔电玩"]
    assert tuzai["storeAlipayWallet"]["name"] == "兔仔电玩支付宝"
    assert tuzai["storeAlipayWallet"]["type"] == WalletType.TAOBAO.value


def test_each_shop_has_five_taobao_wallets_in_db(client, tmp_path):
    db = database.SessionLocal()
    try:
        shops = db.scalars(select(TaobaoShop)).all()
        assert len(shops) == 3
        for shop in shops:
            # 5 个店铺钱包：支付宝支付在途/微信支付在途/聚合冻结/聚合可提现/银行卡
            taobao_wallets = db.scalars(
                select(Wallet).where(
                    Wallet.parent_id.is_(None),
                    Wallet.type == WalletType.TAOBAO.value,
                    Wallet.name.like(f"{shop.name} %"),
                )
            ).all()
            assert len(taobao_wallets) == 5
            assert {w.currency for w in taobao_wallets} == {Currency.CNY.value}
    finally:
        db.close()


def test_ensure_default_taobao_wallets_is_idempotent(client):
    db = database.SessionLocal()
    try:
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

        # 3 shops * 5 wallets + 兔仔电玩支付宝(type=TAOBAO) = 16
        assert before_taobao_count == after_taobao_count == 16
        assert before_shop_count == after_shop_count == 3
    finally:
        db.close()


def test_tuzai_store_alipay_is_not_in_asset_tree(client):
    """兔仔的店铺支付宝是 type=TAOBAO,不应出现在 GET /wallets/assets 树中。"""
    response = client.get("/wallets/assets")
    assert response.status_code == 200
    assets = response.json()

    def collect_names(nodes: list) -> set[str]:
        names: set[str] = set()
        for node in nodes:
            names.add(node["name"])
            children = node.get("children") or []
            names |= collect_names(children)
        return names

    all_names = collect_names(assets)
    assert "兔仔电玩支付宝" not in all_names


def test_taobao_wallet_names_use_renamed_suffixes(client):
    """钱包名称使用新的后缀：支付宝支付在途 / 微信支付在途。"""
    db = database.SessionLocal()
    try:
        names = {
            w.name
            for w in db.scalars(
                select(Wallet).where(
                    Wallet.parent_id.is_(None),
                    Wallet.type == WalletType.TAOBAO.value,
                )
            ).all()
        }
        # 新后缀必须存在
        assert "丙火电玩 支付宝支付在途" in names
        assert "丙火电玩 微信支付在途" in names
        assert "兔仔电玩 支付宝支付在途" in names
        assert "小小电玩 微信支付在途" in names
        # 旧后缀不应再出现
        for old_name in (
            "丙火电玩 支付宝在途",
            "丙火电玩 微信在途",
            "兔仔电玩 支付宝在途",
        ):
            assert old_name not in names
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
