"""Asset wallet service functions."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.wallet import Currency, Wallet, WalletType, create_wallet


ASSET_TYPES = {WalletType.ASSET_RMB.value, WalletType.ASSET_USDT.value}
DEFAULT_ASSET_WALLETS = (
    {
        "name": "RMB钱包",
        "wallet_type": WalletType.ASSET_RMB,
        "currency": Currency.CNY,
        "groups": (
            {
                "name": "支付宝钱包",
                "children": ("丙火网络支付宝", "TOM支付宝", "BOSS支付宝"),
            },
            {
                "name": "微信钱包",
                "children": ("跳舞姬微信",),
            },
        ),
    },
    {
        "name": "USDT钱包",
        "wallet_type": WalletType.ASSET_USDT,
        "currency": Currency.USDT,
        "children": ("FREEMAN币安", "张总币安"),
    },
)


def ensure_default_asset_wallets(session: Session) -> None:
    """Create or migrate the default asset wallet tree idempotently."""
    for config in DEFAULT_ASSET_WALLETS:
        root = session.scalar(
            select(Wallet).where(
                Wallet.type == config["wallet_type"].value,
                Wallet.currency == config["currency"].value,
                Wallet.parent_id.is_(None),
            )
        )
        if root is None:
            root = create_wallet(
                session,
                name=config["name"],
                wallet_type=config["wallet_type"],
                currency=config["currency"],
                is_group=True,
            )
        else:
            root.name = config["name"]
            root.is_group = True
            root.balance = Decimal("0")

        for group_config in config.get("groups", ()):
            group = ensure_sub_wallet(session, root, group_config["name"], is_group=True)
            group.balance = Decimal("0")
            for child_name in group_config["children"]:
                ensure_sub_wallet(session, group, child_name, is_group=False)

        for child_name in config.get("children", ()):
            ensure_sub_wallet(session, root, child_name, is_group=False)
    session.flush()


def ensure_sub_wallet(session: Session, parent: Wallet, name: str, is_group: bool = False) -> Wallet:
    """Create a named child wallet under a parent if it does not exist."""
    existing = session.scalar(
        select(Wallet).where(
            Wallet.parent_id == parent.id,
            Wallet.name == name,
        )
    )
    if existing is not None:
        existing.is_group = is_group
        if is_group:
            existing.balance = Decimal("0")
        return existing

    return create_wallet(
        session,
        name=name,
        wallet_type=parent.type.value if isinstance(parent.type, WalletType) else parent.type,
        currency=parent.currency.value if isinstance(parent.currency, Currency) else parent.currency,
        parent_id=parent.id,
        opening_balance=Decimal("0"),
        is_group=is_group,
    )


def is_asset_wallet(wallet: Wallet) -> bool:
    wallet_type = wallet.type.value if isinstance(wallet.type, WalletType) else wallet.type
    return wallet_type in ASSET_TYPES


def list_asset_wallets(session: Session) -> list[Wallet]:
    return list(
        session.scalars(
            select(Wallet)
            .where(Wallet.type.in_(ASSET_TYPES))
            .order_by(Wallet.parent_id.is_not(None), Wallet.id)
        )
    )


def create_asset_sub_wallet(session: Session, parent: Wallet, name: str, is_group: bool = False) -> Wallet:
    if not is_asset_wallet(parent):
        raise ValueError("parent wallet is not an asset wallet")
    return ensure_sub_wallet(session, parent, name, is_group=is_group)
