"""客服身份认证 + 账号领取相关模型。

CEO 2026-05-11 确认:
- 客服需要登录(账号 + 密码 + Google 二步)
- 账号库存有"可出库"状态(CEO 后台手动标)
- 客服可领取可出库账号,每人同时最多 3 个,一账号同时只能 1 人领
- 下班手动归还(无自动兜底)
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.database import Base
from src.utils.time import china_now


class Operator(Base):
    """客服账号(独立于 XBOX 账号,这是销售系统的用户)。"""

    __tablename__ = "operators"

    id: Mapped[int] = mapped_column(primary_key=True)
    # 登录账号(唯一,客服自己用的登录名)
    login_name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    # 显示名(销售记录上自动填这个)
    display_name: Mapped[str] = mapped_column(String(64), nullable=False)
    # bcrypt 哈希后的登录密码
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # Google Authenticator TOTP 密钥(base32 编码,登录时校验 6 位验证码)
    # 创建客服时自动生成,客服首次登录前需要在系统里看二维码扫码绑定
    totp_secret: Mapped[str] = mapped_column(String(64), nullable=False)
    # TOTP 是否已被客服扫码绑定（首次显示二维码,扫完点确认后置 True）
    totp_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    # 是否激活(停用后无法登录)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    remark: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=china_now,
    )
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class XboxAccountClaim(Base):
    """XBOX 账号领取记录。

    业务规则:
    - 一个账号同时只能被 1 个客服领(`is_active=True` 状态下唯一约束)
    - 一个客服同时最多 3 个有效领取(应用层校验)
    - 归还后 `returned_at` 写时间, `is_active=False`,允许其他人再领
    """

    __tablename__ = "xbox_account_claims"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("xbox_accounts.id"), nullable=False, index=True
    )
    operator_id: Mapped[int] = mapped_column(
        ForeignKey("operators.id"), nullable=False, index=True
    )
    claimed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=china_now,
    )
    returned_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # is_active 标记是否当前生效的领取(归还后变 False)
    # 用 SQL 唯一索引保证: 同一账号同一时刻只能有 1 条 is_active=True
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    return_reason: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )  # "manual" / "force_recall_by_admin"
