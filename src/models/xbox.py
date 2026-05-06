"""XBOX account and transaction ORM models."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base
from src.utils.time import china_now


class XboxCountry(str, Enum):
    US = "US"
    UK = "UK"


class XboxCurrency(str, Enum):
    USD = "USD"
    GBP = "GBP"


class XboxTransactionType(str, Enum):
    RECHARGE = "recharge"
    CONSUME = "consume"


class XboxAccount(Base):
    __tablename__ = "xbox_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    country: Mapped[XboxCountry] = mapped_column(String(8), nullable=False)
    currency: Mapped[XboxCurrency] = mapped_column(String(8), nullable=False)
    rmb_cost: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("0"))
    local_balance: Mapped[Decimal] = mapped_column(
        Numeric(18, 6),
        nullable=False,
        default=Decimal("0"),
    )
    remark: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=china_now,
    )

    transactions: Mapped[list["XboxTransaction"]] = relationship(
        back_populates="account",
        cascade="all, delete-orphan",
    )


class XboxTransaction(Base):
    __tablename__ = "xbox_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("xbox_accounts.id"), nullable=False, index=True)
    rmb_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("0"))
    local_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    type: Mapped[XboxTransactionType] = mapped_column(String(16), nullable=False)
    remark: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=china_now,
    )

    account: Mapped[XboxAccount] = relationship(back_populates="transactions")
