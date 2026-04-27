"""Asset wallet service functions."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.wallet import Currency, Wallet, WalletType, create_wallet


ASSET_TYPES = {WalletType.ASSET_RMB.value, WalletType.ASSET_USDT.value}
DEFAULT_ASSET_WALLETS = (
    {
        "name": "RMB Main",
        "wallet_type": WalletType.ASSET_RMB,
        "currency": Currency.CNY,
    },
    {
        "name": "USDT Main",
        "wallet_type": WalletType.ASSET_USDT,
        "currency": Currency.USDT,
    },
)


def ensure_default_asset_wallets(session: Session) -> None:
    """Create RMB and USDT root asset wallets if they do not already exist."""
    for config in DEFAULT_ASSET_WALLETS:
        exists = session.scalar(
            select(Wallet).where(
                Wallet.type == config["wallet_type"].value,
                Wallet.currency == config["currency"].value,
                Wallet.parent_id.is_(None),
            )
        )
        if exists is None:
            create_wallet(
                session,
                name=config["name"],
                wallet_type=config["wallet_type"],
                currency=config["currency"],
            )
    session.flush()


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


def create_asset_sub_wallet(session: Session, parent: Wallet, name: str) -> Wallet:
    if not is_asset_wallet(parent):
        raise ValueError("parent wallet is not an asset wallet")
    return create_wallet(
        session,
        name=name,
        wallet_type=parent.type.value if isinstance(parent.type, WalletType) else parent.type,
        currency=parent.currency.value if isinstance(parent.currency, Currency) else parent.currency,
        parent_id=parent.id,
        opening_balance=Decimal("0"),
    )
