"""Database configuration and initialization helpers."""
from __future__ import annotations

import os
from typing import Iterator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./finance.db")


class Base(DeclarativeBase):
    """Base class for SQLAlchemy ORM models."""


def _connect_args(database_url: str) -> dict:
    if database_url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}


engine = create_engine(DATABASE_URL, connect_args=_connect_args(DATABASE_URL))
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def configure_database(database_url: str) -> None:
    """Reconfigure the database connection, mainly for isolated tests."""
    global DATABASE_URL, SessionLocal, engine

    DATABASE_URL = database_url
    engine = create_engine(DATABASE_URL, connect_args=_connect_args(DATABASE_URL))
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    """Create all database tables used by the finance system."""
    # Import models so their metadata is registered before create_all runs.
    from src.models import wallet  # noqa: F401
    from src.models import vendor  # noqa: F401
    from src.models import xbox  # noqa: F401
    from src.models import taobao  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _ensure_wallet_is_group_column()
    _ensure_wallet_transaction_business_date_column()
    _ensure_xbox_account_extended_columns()


def _ensure_wallet_is_group_column() -> None:
    """Add the wallet group marker to existing SQLite dev databases."""
    if not DATABASE_URL.startswith("sqlite"):
        return

    inspector = inspect(engine)
    if "wallets" not in inspector.get_table_names():
        return

    column_names = {column["name"] for column in inspector.get_columns("wallets")}
    if "is_group" in column_names:
        return

    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE wallets ADD COLUMN is_group BOOLEAN NOT NULL DEFAULT 0"))


def _ensure_xbox_account_extended_columns() -> None:
    """Add XBOX account 扩展字段（PR #103 / issue #102）。

    旧 SQLite 库 ``xbox_accounts`` 只有 6 个字段,新版加：
    account_no / login_email / password_enc / exchange_rate /
    status / status_message / last_synced_at
    """
    if not DATABASE_URL.startswith("sqlite"):
        return

    inspector = inspect(engine)
    if "xbox_accounts" not in inspector.get_table_names():
        return

    column_names = {column["name"] for column in inspector.get_columns("xbox_accounts")}

    additions = [
        ("account_no", "VARCHAR(64)"),
        ("login_email", "VARCHAR(255)"),
        ("password_enc", "TEXT"),
        ("exchange_rate", "NUMERIC(12, 6)"),
        ("status", "VARCHAR(32) NOT NULL DEFAULT 'active'"),
        ("status_message", "TEXT"),
        ("last_synced_at", "DATETIME"),
    ]

    with engine.begin() as connection:
        for col_name, col_def in additions:
            if col_name not in column_names:
                connection.execute(
                    text(f"ALTER TABLE xbox_accounts ADD COLUMN {col_name} {col_def}")
                )

        # account_no 唯一索引（重复运行幂等：CREATE INDEX IF NOT EXISTS）
        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_xbox_accounts_account_no "
                "ON xbox_accounts(account_no) WHERE account_no IS NOT NULL"
            )
        )


def _ensure_wallet_transaction_business_date_column() -> None:
    """Add WalletTransaction.business_date for existing SQLite dev databases.

    business_date 用于聚合可提现 IN 流水标记业务日期(=mature_at 那天),
    daily-summary 端点据此聚合。见 .claude/skills/taobao-cashflow-rules。
    """
    if not DATABASE_URL.startswith("sqlite"):
        return

    inspector = inspect(engine)
    if "wallet_transactions" not in inspector.get_table_names():
        return

    column_names = {column["name"] for column in inspector.get_columns("wallet_transactions")}
    if "business_date" in column_names:
        return

    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE wallet_transactions ADD COLUMN business_date DATE"))


def get_db() -> Iterator[Session]:
    """Yield a database session for future FastAPI dependencies."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
