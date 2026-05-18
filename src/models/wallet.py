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
    # CEO 2026-05-18: 记录这笔流水是谁操作的(目前财务系统由 CEO 一个人用,
    # 前端从 localStorage 拿,允许财务记录"是我还是李睿旭"按的钱)
    operator_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
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
    # Issue #129: 关联划转单(钱包间转账). 一笔划转 = 两条 wallet_transactions
    # (一 OUT 一 IN), 用 transfer_id 绑死. 普通的 credit/debit 流水留 NULL.
    transfer_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("wallet_transfers.id"),
        nullable=True,
        index=True,
    )

    wallet: Mapped[Wallet] = relationship(back_populates="transactions")


class WalletTransfer(Base):
    """划转单 — 一笔钱从 A 钱包搬到 B 钱包, 记录两边金额和汇率快照.

    Issue #129 (CEO 2026-05-18):
    - 典型场景: 台湾同事把 TWD 兑成 USDT 打到资产钱包, 一条 transfer = 两条 tx
    - 用户填两个金额 (出账/入账), 系统自动算 rate = to_amount / from_amount
    - from_currency / to_currency 必须**快照**, 防钱包后续改名/改币种导致历史汇率失真
    - 软删除 (deleted_at) 用于"撤销划转": 反向冲销两条流水 + 标记 deleted_at
    """

    __tablename__ = "wallet_transfers"

    id: Mapped[int] = mapped_column(primary_key=True)
    from_wallet_id: Mapped[int] = mapped_column(ForeignKey("wallets.id"), nullable=False, index=True)
    to_wallet_id: Mapped[int] = mapped_column(ForeignKey("wallets.id"), nullable=False, index=True)
    from_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    to_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    # 汇率精度比金额高 2 位, 保留 8 位小数足够覆盖 USDT/CNY/TWD 间小数级别波动
    rate: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    from_currency: Mapped[str] = mapped_column(String(8), nullable=False)
    to_currency: Mapped[str] = mapped_column(String(8), nullable=False)
    business_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    operator_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=china_now,
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    from_wallet: Mapped[Wallet] = relationship(foreign_keys=[from_wallet_id])
    to_wallet: Mapped[Wallet] = relationship(foreign_keys=[to_wallet_id])


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
    remark: str | None = None,
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
        remark=remark,
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
    operator_name: str | None = None,
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
        mature_at=mature_at,
        business_date=business_date,
        operator_name=operator_name,
    )
    session.add(transaction)
    session.flush()
    return transaction


def debit(
    session: Session,
    wallet_id: int,
    amount: Decimal | int | float | str,
    remark: str | None = None,
    operator_name: str | None = None,
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
        operator_name=operator_name,
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
