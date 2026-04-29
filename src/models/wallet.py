"""Wallet models and balance movement helpers."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, Text, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from src.database import Base


class WalletType(str, Enum):
    ASSET_RMB = "ASSET_RMB"
    ASSET_USDT = "ASSET_USDT"
    VENDOR = "VENDOR"
    XBOX = "XBOX"
    TAOBAO = "TAOBAO"
    TAIWAN = "TAIWAN"


class Currency(str, Enum):
    CNY = "CNY"
    USDT = "USDT"
    USD = "USD"
    GBP = "GBP"
    TWD = "TWD"


class TransactionDirection(str, Enum):
    IN = "in"
    OUT = "out"


class Wallet(Base):
    __tablename__ = "wallets"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    type: Mapped[WalletType] = mapped_column(String(32), nullable=False)
    currency: Mapped[Currency] = mapped_column(String(16), nullable=False)
    balance: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("0"))
    is_group: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("wallets.id"), nullable=True)
    remark: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    parent: Mapped[Optional["Wallet"]] = relationship(
        remote_side=[id],
        back_populates="children",
    )
    children: Mapped[list["Wallet"]] = relationship(back_populates="parent")
    transactions: Mapped[list["WalletTransaction"]] = relationship(
        back_populates="wallet",
        cascade="all, delete-orphan",
    )


class WalletTransaction(Base):
    __tablename__ = "wallet_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    wallet_id: Mapped[int] = mapped_column(ForeignKey("wallets.id"), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    direction: Mapped[TransactionDirection] = mapped_column(String(8), nullable=False)
    remark: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    wallet: Mapped[Wallet] = relationship(back_populates="transactions")


def _to_decimal(amount: Decimal | int | float | str) -> Decimal:
    value = Decimal(str(amount))
    if value <= 0:
        raise ValueError("amount must be greater than zero")
    return value


def get_wallet(session: Session, wallet_id: int) -> Wallet:
    wallet = session.get(Wallet, wallet_id)
    if wallet is None:
        raise ValueError(f"wallet {wallet_id} does not exist")
    return wallet


def create_wallet(
    session: Session,
    *,
    name: str,
    wallet_type: WalletType | str,
    currency: Currency | str,
    parent_id: int | None = None,
    opening_balance: Decimal | int | float | str = Decimal("0"),
    is_group: bool = False,
) -> Wallet:
    """Create a wallet or sub-wallet and flush it into the current session."""
    balance = Decimal(str(opening_balance))
    if balance < 0:
        raise ValueError("opening_balance cannot be negative")
    if is_group:
        balance = Decimal("0")
    if parent_id is not None:
        get_wallet(session, parent_id)

    wallet = Wallet(
        name=name,
        type=WalletType(wallet_type),
        currency=Currency(currency),
        parent_id=parent_id,
        balance=balance,
        is_group=is_group,
    )
    session.add(wallet)
    session.flush()
    return wallet


def credit(
    session: Session,
    wallet_id: int,
    amount: Decimal | int | float | str,
    remark: str | None = None,
) -> WalletTransaction:
    """Increase a wallet balance and create an inbound transaction record."""
    value = _to_decimal(amount)
    wallet = get_wallet(session, wallet_id)
    wallet.balance = Decimal(wallet.balance) + value

    transaction = WalletTransaction(
        wallet_id=wallet_id,
        amount=value,
        direction=TransactionDirection.IN,
        remark=remark,
    )
    session.add(transaction)
    session.flush()
    return transaction


def debit(
    session: Session,
    wallet_id: int,
    amount: Decimal | int | float | str,
    remark: str | None = None,
) -> WalletTransaction:
    """Decrease a wallet balance and create an outbound transaction record."""
    value = _to_decimal(amount)
    wallet = get_wallet(session, wallet_id)
    wallet_type = wallet.type.value if isinstance(wallet.type, WalletType) else wallet.type
    if wallet_type != WalletType.VENDOR.value and Decimal(wallet.balance) < value:
        raise ValueError("insufficient wallet balance")

    wallet.balance = Decimal(wallet.balance) - value
    transaction = WalletTransaction(
        wallet_id=wallet_id,
        amount=value,
        direction=TransactionDirection.OUT,
        remark=remark,
    )
    session.add(transaction)
    session.flush()
    return transaction


def list_transactions(session: Session, wallet_id: int) -> list[WalletTransaction]:
    get_wallet(session, wallet_id)
    return list(
        session.scalars(
            select(WalletTransaction)
            .where(WalletTransaction.wallet_id == wallet_id)
            .order_by(WalletTransaction.id)
        )
    )
