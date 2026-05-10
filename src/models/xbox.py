"""XBOX account and transaction ORM models。

PR #103 (issue #102): 按 XBOX 订单板块需求文档 v1.0 升级账号库存。
PR #110 (issue P0.2): 加同步订单 / 销售记录 / 余额快照 / 同步批次 / 钱包设置。
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, JSON, Numeric, String, Text
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


# ===================================================================
# PR #110 P0.2 — 订单 / 销售记录 / 余额快照 / 同步批次 / 钱包设置
# ===================================================================


class XboxOrderStatus(str, Enum):
    """订单状态。"""

    PENDING_COMPLETE = "pending_complete"  # 待补齐业务字段
    CONVERTED = "converted"  # 已转销售记录


class XboxOrder(Base):
    """同步订单（FR-04 抓取或手动建,FR-05 补齐后转销售）。"""

    __tablename__ = "xbox_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("xbox_accounts.id"), nullable=False, index=True
    )
    order_no: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    # Microsoft 订单原始信息
    amount_local: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal("0")
    )  # 本币消费金额（如 USD $100）
    currency_local: Mapped[str] = mapped_column(String(8), nullable=False)  # USD / GBP
    exchange_rate: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(12, 6), nullable=True
    )  # 用了哪个汇率（默认从账号取）
    rmb_cost: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal("0")
    )  # = amount_local * exchange_rate
    order_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_data: Mapped[Optional[str]] = mapped_column(JSON, nullable=True)
    # 状态
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=XboxOrderStatus.PENDING_COMPLETE.value
    )
    # 补齐字段（运营填写）
    sale_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    product_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    operator_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    sale_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 6), nullable=True)
    sale_currency: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    wallet_method_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("xbox_wallet_methods.id"), nullable=True
    )
    wallet_item_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("xbox_wallet_items.id"), nullable=True
    )
    # 关联（方案 3 双向）
    sale_record_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("xbox_sale_records.id"), nullable=True, index=True
    )
    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=china_now
    )
    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=china_now
    )

    account: Mapped[XboxAccount] = relationship()
    sale_record: Mapped[Optional["XboxSaleRecord"]] = relationship(
        back_populates="orders", foreign_keys=[sale_record_id]
    )


class XboxSaleRecord(Base):
    """销售记录（订单补齐后生成,带 walletPoolId 流入资金池）。"""

    __tablename__ = "xbox_sale_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("xbox_accounts.id"), nullable=False, index=True
    )
    sale_date: Mapped[date] = mapped_column(Date, nullable=False)
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    operator_name: Mapped[str] = mapped_column(String(64), nullable=False)
    # 售价（合单后总金额,可改）
    sale_price: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), nullable=False, default=Decimal("0")
    )
    sale_currency: Mapped[str] = mapped_column(String(8), nullable=False)  # CNY/USD/USDT/TWD
    # 钱包设置映射
    wallet_method_id: Mapped[int] = mapped_column(
        ForeignKey("xbox_wallet_methods.id"), nullable=False
    )
    wallet_item_id: Mapped[int] = mapped_column(
        ForeignKey("xbox_wallet_items.id"), nullable=False
    )
    wallet_item_label: Mapped[str] = mapped_column(String(120), nullable=False)  # 备注模板展示标签
    wallet_pool_id: Mapped[int] = mapped_column(
        ForeignKey("wallets.id"), nullable=False, index=True
    )  # 资金池=具体钱包 id（CEO Q1C）
    # 内部记账：本销售记录在资金池写入了一笔 IN 流水（用于改字段时反向调整）
    bookkeeping_tx_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("wallet_transactions.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=china_now
    )
    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=china_now
    )

    account: Mapped[XboxAccount] = relationship()
    orders: Mapped[list["XboxOrder"]] = relationship(
        back_populates="sale_record",
        foreign_keys=[XboxOrder.sale_record_id],
    )


class XboxBalanceSnapshot(Base):
    """账号本币余额快照（FR-04 同步时记录）。"""

    __tablename__ = "xbox_balance_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("xbox_accounts.id"), nullable=False, index=True
    )
    currency: Mapped[str] = mapped_column(String(8), nullable=False)
    balance: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=china_now
    )

    account: Mapped[XboxAccount] = relationship()


class XboxSyncBatch(Base):
    """同步批次（FR-04 每次抓取记一条,P0.2 先建表,真同步在 P2）。"""

    __tablename__ = "xbox_sync_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("xbox_accounts.id"), nullable=False, index=True
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=china_now
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    requested_count: Mapped[int] = mapped_column(default=0)
    fetched_count: Mapped[int] = mapped_column(default=0)
    success: Mapped[bool] = mapped_column(default=False)
    failure_category: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    failure_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    account: Mapped[XboxAccount] = relationship()


class XboxWalletMethod(Base):
    """钱包设置 - 收款方式（如"代理"、"自营"）。

    财务系统通过 PUT /xbox/wallet-settings 推送同步过来。
    """

    __tablename__ = "xbox_wallet_methods"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=china_now
    )
    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=china_now
    )

    items: Mapped[list["XboxWalletItem"]] = relationship(
        back_populates="method",
        cascade="all, delete-orphan",
    )


class XboxWalletItem(Base):
    """钱包设置 - 备注模板（如"代理 001"、"代理 002"）→ 资金池映射。"""

    __tablename__ = "xbox_wallet_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    method_id: Mapped[int] = mapped_column(
        ForeignKey("xbox_wallet_methods.id"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    wallet_pool_id: Mapped[int] = mapped_column(
        ForeignKey("wallets.id"), nullable=False
    )  # 资金池=具体钱包
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=china_now
    )
    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=china_now
    )

    method: Mapped[XboxWalletMethod] = relationship(back_populates="items")


class XboxChangeLog(Base):
    """订单 / 销售记录改字段的变更审计（CEO 2026-05-08 Q3:A）。

    通用日志表,entity_type 标识来自哪种实体（order / sale_record）。
    每次改字段、改资金池、改售价等都记一条,便于事后追溯"谁什么时候改了什么"。
    """

    __tablename__ = "xbox_change_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # entity_type 取值: "order" / "sale_record"
    entity_id: Mapped[int] = mapped_column(nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    # action 取值: "created" / "updated" / "completed" / "merged" / "wallet_pool_changed"
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    operator: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=china_now,
    )
