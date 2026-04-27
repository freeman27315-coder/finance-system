"""Taobao account ORM model."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base
from src.models.wallet import Wallet


class TaobaoAccount(Base):
    __tablename__ = "taobao_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    unsettled_wallet_id: Mapped[int] = mapped_column(ForeignKey("wallets.id"), nullable=False)
    settled_wallet_id: Mapped[int] = mapped_column(ForeignKey("wallets.id"), nullable=False)
    remark: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    unsettled_wallet: Mapped[Wallet] = relationship(foreign_keys=[unsettled_wallet_id])
    settled_wallet: Mapped[Wallet] = relationship(foreign_keys=[settled_wallet_id])
