"""Vendor wallet service functions."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.vendor import Vendor
from src.models.wallet import Currency, Wallet, WalletType, create_wallet


def create_vendor_wallet(session: Session, vendor_name: str) -> Wallet:
    """Create the dedicated RMB wallet attached to a vendor."""
    return create_wallet(
        session,
        name=f"{vendor_name} 账单",
        wallet_type=WalletType.VENDOR,
        currency=Currency.CNY,
        is_group=False,
    )


def ensure_vendor_wallets(session: Session) -> None:
    """Idempotently create a VENDOR wallet for any vendor missing one."""
    vendors = session.scalars(select(Vendor).where(Vendor.wallet_id.is_(None))).all()
    for vendor in vendors:
        wallet = create_vendor_wallet(session, vendor.name)
        vendor.wallet_id = wallet.id
    session.flush()
