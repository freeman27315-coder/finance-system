"""Taobao shop service functions."""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.taobao import TaobaoShop
from src.models.wallet import Currency, Wallet, WalletType, create_wallet


# 每店铺自动建的 5 个 TAOBAO 钱包后缀
TAOBAO_SHOP_WALLET_SUFFIXES = (
    "支付宝支付在途",
    "微信支付在途",
    "聚合支付·冻结中",
    "聚合支付·可提现",
    "银行卡",
)

# 兔仔的店铺支付宝钱包名（type=TAOBAO 顶级,非资产页可见）
TUZAI_STORE_ALIPAY_WALLET_NAME = "兔仔电玩支付宝"

# 3 个店铺的初始化配置
# store_alipay_wallet_name 为支付宝钱包分组下的子钱包名（兔仔为 None,改为单建 TAOBAO 钱包）
DEFAULT_TAOBAO_SHOPS = (
    {"name": "丙火网络", "store_alipay_wallet_name": "丙火网络支付宝"},
    {"name": "兔仔电玩", "store_alipay_wallet_name": None},
    {"name": "小小电玩", "store_alipay_wallet_name": "小小电玩支付宝"},
)


def _find_alipay_group(session: Session) -> Wallet:
    """Find the '支付宝钱包' group wallet under ASSET_RMB."""
    group = session.scalar(
        select(Wallet).where(
            Wallet.type == WalletType.ASSET_RMB.value,
            Wallet.currency == Currency.CNY.value,
            Wallet.name == "支付宝钱包",
            Wallet.is_group.is_(True),
        )
    )
    if group is None:
        raise RuntimeError(
            "未找到支付宝钱包分组，请先调用 ensure_default_asset_wallets"
        )
    return group


def _ensure_alipay_sub_wallet(session: Session, name: str) -> Wallet:
    """Ensure a sub-wallet exists under the 支付宝钱包 group; create if missing."""
    alipay_group = _find_alipay_group(session)
    existing = session.scalar(
        select(Wallet).where(
            Wallet.parent_id == alipay_group.id,
            Wallet.name == name,
        )
    )
    if existing is not None:
        return existing
    return create_wallet(
        session,
        name=name,
        wallet_type=WalletType.ASSET_RMB,
        currency=Currency.CNY,
        parent_id=alipay_group.id,
        is_group=False,
    )


def _ensure_taobao_wallet(session: Session, name: str) -> Wallet:
    """Ensure a top-level TAOBAO wallet with the given name; create if missing."""
    existing = session.scalar(
        select(Wallet).where(
            Wallet.parent_id.is_(None),
            Wallet.type == WalletType.TAOBAO.value,
            Wallet.name == name,
        )
    )
    if existing is not None:
        return existing
    return create_wallet(
        session,
        name=name,
        wallet_type=WalletType.TAOBAO,
        currency=Currency.CNY,
        is_group=False,
    )


def ensure_default_taobao_wallets(session: Session) -> None:
    """Idempotently provision the 3 Taobao shops with their wallets.

    Run order:
      1. 在资产支付宝下补建 '小小电玩支付宝' 子钱包（如缺失）
      2. 创建 3 个 TaobaoShop（已存在则跳过）
      3. 每店铺自动建 5 个 TAOBAO 钱包（支付宝支付在途/微信支付在途/聚合冻结/聚合可提现/银行卡）
      4. 兔仔的 store_alipay_wallet 指向独立的 type=TAOBAO 顶级钱包"兔仔电玩支付宝"
         （账面记账,不在 GET /wallets/assets 树中可见）
    """
    # 1. 先确保 "小小电玩支付宝" 在 支付宝钱包 分组下存在
    _ensure_alipay_sub_wallet(session, "小小电玩支付宝")

    # 2. 创建/复用 3 个店铺
    for shop_config in DEFAULT_TAOBAO_SHOPS:
        shop_name: str = shop_config["name"]
        store_alipay_wallet_name: Optional[str] = shop_config["store_alipay_wallet_name"]

        existing_shop = session.scalar(
            select(TaobaoShop).where(TaobaoShop.name == shop_name)
        )
        if existing_shop is not None:
            continue

        # 3. 为店铺建 5 个 TAOBAO 钱包（顶级，无 parent）
        wallets: list[Wallet] = []
        for suffix in TAOBAO_SHOP_WALLET_SUFFIXES:
            wallet = _ensure_taobao_wallet(session, f"{shop_name} {suffix}")
            wallets.append(wallet)

        # 4. 解析店铺支付宝钱包：
        #    - A 类（丙火/小小）：在资产支付宝下找/建
        #    - B 类（兔仔）：单建 type=TAOBAO 顶级钱包"兔仔电玩支付宝"
        if store_alipay_wallet_name:
            store_alipay_wallet = _ensure_alipay_sub_wallet(session, store_alipay_wallet_name)
        else:
            store_alipay_wallet = _ensure_taobao_wallet(session, TUZAI_STORE_ALIPAY_WALLET_NAME)

        shop = TaobaoShop(
            name=shop_name,
            store_alipay_wallet_id=store_alipay_wallet.id,
            unconfirmed_alipay_wallet_id=wallets[0].id,
            unconfirmed_wechat_wallet_id=wallets[1].id,
            aggregator_frozen_wallet_id=wallets[2].id,
            aggregator_available_wallet_id=wallets[3].id,
            bank_card_wallet_id=wallets[4].id,
        )
        session.add(shop)

    session.flush()


def list_taobao_shops(session: Session) -> list[TaobaoShop]:
    return list(
        session.scalars(select(TaobaoShop).order_by(TaobaoShop.id))
    )


def ensure_shop_total_group_wallets(session: Session) -> dict[str, int]:
    """CEO 2026-05-08: 给每家淘宝店建 group 总钱包,统管它的 5 或 6 个 TAOBAO 钱包。

    新建：
    - 丙火网络（group, TAOBAO, CNY）  ← 统管丙火 5 个钱包
    - 兔仔电玩（group, TAOBAO, CNY）  ← 统管兔仔 6 个（含店铺支付宝）
    - 小小电玩（group, TAOBAO, CNY）  ← 统管小小 5 个钱包

    把现有 TAOBAO 类型 + parent_id IS NULL 的钱包按名字前缀挂到对应总钱包下。

    丙火网络支付宝/小小电玩支付宝在 ASSET_RMB 下,**不动**(跨大类不能挂)。
    对账时通过 1:N 映射手动挂上即可（CEO Q1A 已确认）。

    返回 ``{店铺名: group_wallet_id}``。幂等可重复运行。
    """
    SHOP_NAMES = ("丙火网络", "兔仔电玩", "小小电玩")
    out: dict[str, int] = {}

    for shop_name in SHOP_NAMES:
        # 找/建总钱包(顶级 group, type=TAOBAO, name=店铺名)
        existing = session.scalar(
            select(Wallet).where(
                Wallet.type == WalletType.TAOBAO.value,
                Wallet.name == shop_name,
                Wallet.parent_id.is_(None),
                Wallet.is_group.is_(True),
            )
        )
        if existing is None:
            existing = create_wallet(
                session,
                name=shop_name,
                wallet_type=WalletType.TAOBAO,
                currency=Currency.CNY,
                is_group=True,
            )
        out[shop_name] = existing.id

        # 把现有以 "{shop_name} " 开头 + parent_id IS NULL 的 TAOBAO 钱包挂到该总钱包下
        # 例：丙火网络 银行卡 / 丙火网络 支付宝支付在途 等
        children = list(
            session.scalars(
                select(Wallet).where(
                    Wallet.type == WalletType.TAOBAO.value,
                    Wallet.parent_id.is_(None),
                    Wallet.id != existing.id,  # 别挂自己到自己下面
                    Wallet.name.like(f"{shop_name} %"),
                )
            )
        )
        for child in children:
            child.parent_id = existing.id

        # 兔仔电玩支付宝: 名字"兔仔电玩支付宝"也挂到 兔仔电玩总钱包 下
        if shop_name == "兔仔电玩":
            tuzai_alipay = session.scalar(
                select(Wallet).where(
                    Wallet.type == WalletType.TAOBAO.value,
                    Wallet.name == "兔仔电玩支付宝",
                    Wallet.parent_id.is_(None),
                )
            )
            if tuzai_alipay is not None:
                tuzai_alipay.parent_id = existing.id

    session.flush()
    return out
