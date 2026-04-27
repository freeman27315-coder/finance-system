"""Vendor and vendor bill ORM models."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base


class VendorBillDirection(str, Enum):
    PAYABLE = "payable"
    RECEIVABLE = "receivable"


class VendorBillStatus(str, Enum):
    PENDING = "pending"
    SETTLED = "settled"


class Vendor(Base):
    __tablename__ = "vendors"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    remark: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    bills: Mapped[list["VendorBill"]] = relationship(
        back_populates="vendor",
        cascade="all, delete-orphan",
    )


class VendorBill(Base):
    __tablename__ = "vendor_bills"

    id: Mapped[int] = mapped_column(primary_key=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id"), nullable=False, index=True)
    direction: Mapped[VendorBillDirection] = mapped_column(String(16), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    status: Mapped[VendorBillStatus] = mapped_column(
        String(16),
        nullable=False,
        default=VendorBillStatus.PENDING.value,
    )
    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    remark: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    vendor: Mapped[Vendor] = relationship(back_populates="bills")
