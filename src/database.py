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


def get_db() -> Iterator[Session]:
    """Yield a database session for future FastAPI dependencies."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
