"""Taobao shop and order ORM models."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base
from src.models.wallet import Wallet


class TaobaoOrderPaymentMethod(str, Enum):
    ALIPAY = "alipay"
    WECHAT = "wechat"


class TaobaoOrderStatus(str, Enum):
    SHIPPED_UNCONFIRMED = "shipped_unconfirmed"  # 卖家已发货,等待买家确认
    RECEIVED = "received"  # 交易成功
    CLOSED = "closed"  # 交易关闭


class TaobaoShop(Base):
    __tablename__ = "taobao_shops"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    store_alipay_wallet_id: Mapped[int] = mapped_column(
        ForeignKey("wallets.id"), nullable=False
    )
    unconfirmed_alipay_wallet_id: Mapped[int] = mapped_column(
        ForeignKey("wallets.id"), nullable=False
    )
    unconfirmed_wechat_wallet_id: Mapped[int] = mapped_column(
        ForeignKey("wallets.id"), nullable=False
    )
    aggregator_frozen_wallet_id: Mapped[int] = mapped_column(
        ForeignKey("wallets.id"), nullable=False
    )
    aggregator_available_wallet_id: Mapped[int] = mapped_column(
        ForeignKey("wallets.id"), nullable=False
    )
    bank_card_wallet_id: Mapped[int] = mapped_column(
        ForeignKey("wallets.id"), nullable=False
    )
    remark: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    store_alipay_wallet: Mapped[Wallet] = relationship(
        foreign_keys=[store_alipay_wallet_id]
    )
    unconfirmed_alipay_wallet: Mapped[Wallet] = relationship(
        foreign_keys=[unconfirmed_alipay_wallet_id]
    )
    unconfirmed_wechat_wallet: Mapped[Wallet] = relationship(
        foreign_keys=[unconfirmed_wechat_wallet_id]
    )
    aggregator_frozen_wallet: Mapped[Wallet] = relationship(
        foreign_keys=[aggregator_frozen_wallet_id]
    )
    aggregator_available_wallet: Mapped[Wallet] = relationship(
        foreign_keys=[aggregator_available_wallet_id]
    )
    bank_card_wallet: Mapped[Wallet] = relationship(
        foreign_keys=[bank_card_wallet_id]
    )


class TaobaoOrder(Base):
    __tablename__ = "taobao_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(
        ForeignKey("taobao_shops.id"), nullable=False, index=True
    )
    order_number: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    payment_method: Mapped[TaobaoOrderPaymentMethod] = mapped_column(
        String(16), nullable=False
    )
    # amount 语义：当前入账钱包的金额。在途 = gross；已确认 = net（gross - fee）
    amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal("0")
    )
    # gross_amount：Excel 原始金额（已确认用 "确认收货打款金额"，在途用 "买家实付金额"）
    gross_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal("0")
    )
    # fee_amount：仅 received 时填值（gross × 0.002，2 位 ROUND_HALF_UP）；在途为 NULL
    fee_amount: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(18, 6), nullable=True
    )
    status: Mapped[TaobaoOrderStatus] = mapped_column(String(32), nullable=False)
    bookkeeping_wallet_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("wallets.id"), nullable=True
    )
    bookkeeping_tx_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("wallet_transactions.id"), nullable=True
    )
    shipped_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    received_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # confirmed_at：来自 Excel "确认收货时间"。微信 mature_at 计算基础。
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    shop: Mapped[TaobaoShop] = relationship(foreign_keys=[shop_id])
