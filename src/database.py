"""Database configuration and initialization helpers."""
from __future__ import annotations

import os
from typing import Iterator

from sqlalchemy import create_engine
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

    Base.metadata.create_all(bind=engine)


def get_db() -> Iterator[Session]:
    """Yield a database session for future FastAPI dependencies."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
