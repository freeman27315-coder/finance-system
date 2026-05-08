"""XBOX account and transaction ORM models。

PR #103 (issue #102): 按 XBOX 订单板块需求文档 v1.0 升级账号库存。
- XboxAccount 加字段：account_no / login_email / password_enc / exchange_rate / status / status_message
- 加 XboxAccountAuditLog 表记录账号变更
- 旧的 XboxTransaction (recharge/consume) 暂保留兼容
"""
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


class XboxAccountStatus(str, Enum):
    """账号状态（CEO 2026-05-08 确认 4 种）。"""

    ACTIVE = "active"  # 可用
    DISABLED = "disabled"  # 停用
    ERROR = "error"  # 异常（密码错 / 登录失败）
    NEED_VERIFICATION = "need_verification"  # 需要安全验证


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
    # PR #103 新增字段
    account_no: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, unique=True, index=True
    )  # 业务唯一编号（加卡系统对接标识）
    login_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    password_enc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # AES-GCM base64
    exchange_rate: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(12, 6), nullable=True
    )  # 账号固定汇率（CEO 选 3C：先按账号锁汇率）
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=XboxAccountStatus.ACTIVE.value
    )
    status_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # 末次同步时间（FR-04 用,P0 先建字段）
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
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
    audit_logs: Mapped[list["XboxAccountAuditLog"]] = relationship(
        back_populates="account",
        cascade="all, delete-orphan",
        order_by="XboxAccountAuditLog.id.desc()",
    )


class XboxAccountAuditLog(Base):
    """账号变更审计日志。

    每次新增 / 改字段 / 改密码 / 改状态 都写一行,用于追溯。
    """

    __tablename__ = "xbox_account_audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("xbox_accounts.id"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    # action 取值：created / updated / password_changed / status_changed
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # detail 是变更摘要,如 "status: active → disabled" 或 "password_changed"
    operator: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    # operator: 操作来源 / 用户标识，P0 先支持 "manual" / "kapian_system" / "internal"
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=china_now,
    )

    account: Mapped[XboxAccount] = relationship(back_populates="audit_logs")


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
