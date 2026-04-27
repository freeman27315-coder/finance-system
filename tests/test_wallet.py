from decimal import Decimal

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from src.database import Base
from src.models.wallet import (
    Currency,
    TransactionDirection,
    Wallet,
    WalletTransaction,
    WalletType,
    create_wallet,
    credit,
    debit,
    list_transactions,
)


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = session_factory()
    try:
        yield db
    finally:
        db.close()


def test_wallet_tables_are_registered():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)

    tables = set(inspect(engine).get_table_names())
    assert {"wallets", "wallet_transactions"}.issubset(tables)


def test_create_parent_and_sub_wallet(session):
    parent = create_wallet(
        session,
        name="RMB Main",
        wallet_type=WalletType.ASSET_RMB,
        currency=Currency.CNY,
    )
    child = create_wallet(
        session,
        name="RMB Sub",
        wallet_type="ASSET_RMB",
        currency="CNY",
        parent_id=parent.id,
    )
    session.commit()

    saved_child = session.get(Wallet, child.id)
    assert saved_child.parent_id == parent.id
    assert saved_child.parent.name == "RMB Main"
    assert saved_child.balance == Decimal("0.000000")


def test_credit_and_debit_create_transactions(session):
    wallet = create_wallet(
        session,
        name="USDT Main",
        wallet_type=WalletType.ASSET_USDT,
        currency=Currency.USDT,
    )

    incoming = credit(session, wallet.id, "150.25", "initial deposit")
    outgoing = debit(session, wallet.id, Decimal("20.25"), "vendor payout")
    session.commit()

    saved_wallet = session.get(Wallet, wallet.id)
    assert saved_wallet.balance == Decimal("130.000000")
    assert incoming.direction == TransactionDirection.IN
    assert outgoing.direction == TransactionDirection.OUT

    transactions = list_transactions(session, wallet.id)
    assert [item.amount for item in transactions] == [Decimal("150.250000"), Decimal("20.250000")]
    assert session.query(WalletTransaction).count() == 2


def test_debit_rejects_insufficient_balance(session):
    wallet = create_wallet(
        session,
        name="Taiwan Wallet",
        wallet_type=WalletType.TAIWAN,
        currency=Currency.TWD,
    )

    with pytest.raises(ValueError, match="insufficient"):
        debit(session, wallet.id, 1)


def test_amount_must_be_positive(session):
    wallet = create_wallet(
        session,
        name="Vendor Wallet",
        wallet_type=WalletType.VENDOR,
        currency=Currency.CNY,
    )

    with pytest.raises(ValueError, match="greater than zero"):
        credit(session, wallet.id, 0)
