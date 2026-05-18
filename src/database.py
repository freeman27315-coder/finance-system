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
    from src.models import operator  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _ensure_wallet_is_group_column()
    _ensure_wallet_transaction_business_date_column()
    _ensure_wallet_transaction_operator_name_column()
    _ensure_wallet_transfers_table()
    _ensure_wallet_transaction_transfer_id_column()
    _ensure_xbox_account_extended_columns()
    _ensure_xbox_account_is_available_for_claim_column()
    _ensure_xbox_account_country_identified_column()
    _ensure_xbox_order_remark_column()
    _migrate_xbox_sale_date_to_datetime()


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


def _ensure_xbox_account_is_available_for_claim_column() -> None:
    """加 XBOX 账号"可出库"字段（CEO 2026-05-11 客服领取流转）。"""
    if not DATABASE_URL.startswith("sqlite"):
        return

    inspector = inspect(engine)
    if "xbox_accounts" not in inspector.get_table_names():
        return

    column_names = {column["name"] for column in inspector.get_columns("xbox_accounts")}
    if "is_available_for_claim" in column_names:
        return

    with engine.begin() as connection:
        connection.execute(
            text("ALTER TABLE xbox_accounts ADD COLUMN is_available_for_claim BOOLEAN NOT NULL DEFAULT 0")
        )


def _ensure_xbox_account_country_identified_column() -> None:
    """加 XBOX 账号"国家是否已识别"字段(CEO 2026-05-12 自动识别国家)。

    业务规则:
    - 新创建账号: country 占位 "US",country_identified=False,首次同步后根据爬到的
      currency 自动改正国家(USD→US, GBP→UK)
    - Q4-B: 旧账号一次性 reset 为 country_identified=False,下次同步重新识别
    """
    if not DATABASE_URL.startswith("sqlite"):
        return

    inspector = inspect(engine)
    if "xbox_accounts" not in inspector.get_table_names():
        return

    column_names = {column["name"] for column in inspector.get_columns("xbox_accounts")}
    if "country_identified" in column_names:
        return

    with engine.begin() as connection:
        # 新列默认 0(False) - 这自动满足 Q4-B(所有旧账号都变成"待识别")
        connection.execute(
            text(
                "ALTER TABLE xbox_accounts ADD COLUMN country_identified "
                "BOOLEAN NOT NULL DEFAULT 0"
            )
        )


def _ensure_xbox_order_remark_column() -> None:
    """加 XBOX 订单"备注"字段(CEO 2026-05-12: 客服补销售可自由填写)。"""
    if not DATABASE_URL.startswith("sqlite"):
        return
    inspector = inspect(engine)
    if "xbox_orders" not in inspector.get_table_names():
        return
    column_names = {column["name"] for column in inspector.get_columns("xbox_orders")}
    if "remark" in column_names:
        return
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE xbox_orders ADD COLUMN remark TEXT"))


def _migrate_xbox_sale_date_to_datetime() -> None:
    """CEO 2026-05-12: 把 xbox_sale_records.sale_date 和 xbox_orders.sale_date
    从 DATE (YYYY-MM-DD) 升级为 DATETIME (YYYY-MM-DD HH:MM:SS.ffffff),
    中国时区精确到秒。

    SQLite 的列类型 affinity 很松散(DATE 和 DATETIME 都是 TEXT 存),所以
    不需要 ALTER COLUMN,只把存量"YYYY-MM-DD"格式的旧值改成
    "YYYY-MM-DD 00:00:00" 让 SQLAlchemy 能按 datetime 解析。
    """
    if not DATABASE_URL.startswith("sqlite"):
        return

    inspector = inspect(engine)
    table_names = inspector.get_table_names()

    with engine.begin() as connection:
        # xbox_sale_records.sale_date (NOT NULL)
        if "xbox_sale_records" in table_names:
            connection.execute(
                text(
                    "UPDATE xbox_sale_records SET sale_date = sale_date || ' 00:00:00' "
                    "WHERE sale_date IS NOT NULL AND length(sale_date) = 10"
                )
            )
        # xbox_orders.sale_date (nullable)
        if "xbox_orders" in table_names:
            connection.execute(
                text(
                    "UPDATE xbox_orders SET sale_date = sale_date || ' 00:00:00' "
                    "WHERE sale_date IS NOT NULL AND length(sale_date) = 10"
                )
            )


def _ensure_wallet_transaction_operator_name_column() -> None:
    """CEO 2026-05-18: 记录每笔流水操作人(从前端 localStorage 传).

    用于台湾钱包 + 之后其他模块的"是谁动了这笔钱"追溯.
    """
    if not DATABASE_URL.startswith("sqlite"):
        return
    inspector = inspect(engine)
    if "wallet_transactions" not in inspector.get_table_names():
        return
    column_names = {column["name"] for column in inspector.get_columns("wallet_transactions")}
    if "operator_name" in column_names:
        return
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE wallet_transactions ADD COLUMN operator_name VARCHAR(120)"))


def _ensure_wallet_transfers_table() -> None:
    """Issue #129: 启动时建 wallet_transfers 表(划转单).

    SQLAlchemy create_all 已经会建表, 这里仅作为防御性 fallback: 若旧库
    metadata 没注册到 WalletTransfer (例如表删了又没重启), 也能补回来.
    """
    if not DATABASE_URL.startswith("sqlite"):
        return
    inspector = inspect(engine)
    if "wallet_transfers" in inspector.get_table_names():
        return
    # 通过 create_all 走 SQLAlchemy 的 DDL 比手写 SQL 更安全; 这里 import 一下确保
    # WalletTransfer 注册进 metadata
    from src.models.wallet import WalletTransfer  # noqa: F401
    Base.metadata.create_all(bind=engine, tables=[WalletTransfer.__table__])


def _ensure_wallet_transaction_transfer_id_column() -> None:
    """Issue #129: 给 wallet_transactions 表加 transfer_id 列(FK + 索引).

    用于把同一笔划转的 OUT/IN 两条流水绑死. 普通 credit/debit 流水留 NULL.
    """
    if not DATABASE_URL.startswith("sqlite"):
        return
    inspector = inspect(engine)
    if "wallet_transactions" not in inspector.get_table_names():
        return
    column_names = {column["name"] for column in inspector.get_columns("wallet_transactions")}
    if "transfer_id" in column_names:
        return
    with engine.begin() as connection:
        # SQLite 加 FK 列只能不带 REFERENCES 约束(SQLite 不支持 ALTER 加 FK).
        # SQLAlchemy ORM 层仍会按 FK 解析; 数据完整性靠业务层保证.
        connection.execute(text("ALTER TABLE wallet_transactions ADD COLUMN transfer_id INTEGER"))
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_wallet_transactions_transfer_id "
                "ON wallet_transactions(transfer_id)"
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
