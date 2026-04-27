"""Taiwan wallet service functions."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.wallet import Currency, Wallet, WalletType, create_wallet


DEFAULT_TAIWAN_WALLET_NAMES = ("8591余额", "银行卡", "超商代收金流余额")


def ensure_default_taiwan_wallets(session: Session) -> None:
    """Create the default Taiwan TWD wallets if they do not already exist."""
    for name in DEFAULT_TAIWAN_WALLET_NAMES:
        exists = session.scalar(
            select(Wallet).where(
                Wallet.type == WalletType.TAIWAN.value,
                Wallet.currency == Currency.TWD.value,
                Wallet.name == name,
                Wallet.parent_id.is_(None),
            )
        )
        if exists is None:
            create_wallet(
                session,
                name=name,
                wallet_type=WalletType.TAIWAN,
                currency=Currency.TWD,
                opening_balance=Decimal("0"),
            )
    session.flush()


def is_taiwan_wallet(wallet: Wallet) -> bool:
    wallet_type = wallet.type.value if isinstance(wallet.type, WalletType) else wallet.type
    currency = wallet.currency.value if isinstance(wallet.currency, Currency) else wallet.currency
    return wallet_type == WalletType.TAIWAN.value and currency == Currency.TWD.value


def list_taiwan_wallets(session: Session) -> list[Wallet]:
    return list(
        session.scalars(
            select(Wallet)
            .where(Wallet.type == WalletType.TAIWAN.value, Wallet.currency == Currency.TWD.value)
            .order_by(Wallet.id)
        )
    )
