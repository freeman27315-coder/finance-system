"""Wallet models and balance movement helpers."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, String, Text, select
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from src.database import Base
from src.utils.time import china_now


class WalletType(str, Enum):
    ASSET_RMB = "ASSET_RMB"
    ASSET_USDT = "ASSET_USDT"
    ASSET_USD = "ASSET_USD"  # PR #110 (P0.2): XBOX USD 销售收入资金池
    VENDOR = "VENDOR"
    XBOX = "XBOX"  # XBOX 账号本身（旧逻辑,不是钱包）
    TAOBAO = "TAOBAO"
    TAIWAN = "TAIWAN"
    # PR P0.2++ XBOX 销售归口"理论值"钱包大类
    # 客服在 XBOX 模块录入销售时选择的"出售渠道"对应的钱包,
    # 与"实际值"(千牛后台导入产生的真实钱包)物理隔离,便于对账
    XBOX_SALES_LEDGER = "XBOX_SALES_LEDGER"


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
        default=china_now,
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
        default=china_now,
    )
    mature_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    # 业务日期标识（仅 IN 流水使用,标记"这笔钱业务上属于哪一天"）：
    # - 聚合释放(_auto_release_aggregator) 写入的 available IN tx：填 mature_at 那天
    # - 其他流水：留 NULL,daily-summary 端点回退用 created_at 或 order 业务日期
    # 见 .claude/skills/taobao-cashflow-rules
    business_date: Mapped[Optional[date]] = mapped_column(
        Date,
        nullable=True,
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
    mature_at: Optional[datetime] = None,
    business_date: Optional[date] = None,
) -> WalletTransaction:
    """Increase a wallet balance and create an inbound transaction record.

    可选 ``mature_at`` 表示该笔入账的"成熟时间"（例如聚合支付冻结期满
    可提现的时间点），仅写入 ``WalletTransaction.mature_at``，不影响余额逻辑。

    可选 ``business_date`` 标记该笔入账的"业务日期"（用于按业务日期聚合）：
    - 聚合释放写入 available IN：业务日期 = mature_at 那天
    - 其他场景留 None，daily-summary 端点会自动回退用 order 业务日期或 created_at
    见 ``.claude/skills/taobao-cashflow-rules``。
    """
    value = _to_decimal(amount)
    wallet = get_wallet(session, wallet_id)
    wallet.balance = Decimal(wallet.balance) + value

    transaction = WalletTransaction(
        wallet_id=wallet_id,
        amount=value,
        direction=TransactionDirection.IN,
        remark=remark,
        mature_at=mature_at,
        business_date=business_date,
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
