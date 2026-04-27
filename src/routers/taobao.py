"""Taobao account API routes."""
from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.database import get_db
from src.models.taobao import TaobaoAccount
from src.models.wallet import Currency, WalletTransaction, WalletType, credit, create_wallet, debit


router = APIRouter(prefix="/taobao", tags=["taobao"])


class TaobaoAccountCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    remark: Optional[str] = None


class TaobaoAccountOut(BaseModel):
    id: int
    name: str
    unsettled_wallet_id: int
    settled_wallet_id: int
    unsettled_balance: Decimal
    settled_balance: Decimal
    remark: Optional[str]
    created_at: str


class TaobaoMovementRequest(BaseModel):
    amount: Decimal = Field(..., gt=0)
    remark: Optional[str] = None


class TaobaoTransactionOut(BaseModel):
    id: int
    wallet_id: int
    wallet_scope: str
    amount: Decimal
    direction: str
    remark: Optional[str]
    created_at: str


def _value(value):
    if isinstance(value, Enum):
        return value.value
    return value


def serialize_account(account: TaobaoAccount) -> TaobaoAccountOut:
    return TaobaoAccountOut(
        id=account.id,
        name=account.name,
        unsettled_wallet_id=account.unsettled_wallet_id,
        settled_wallet_id=account.settled_wallet_id,
        unsettled_balance=account.unsettled_wallet.balance,
        settled_balance=account.settled_wallet.balance,
        remark=account.remark,
        created_at=account.created_at.isoformat() if account.created_at else "",
    )


def serialize_transaction(account: TaobaoAccount, transaction: WalletTransaction) -> TaobaoTransactionOut:
    scope = "unsettled" if transaction.wallet_id == account.unsettled_wallet_id else "settled"
    return TaobaoTransactionOut(
        id=transaction.id,
        wallet_id=transaction.wallet_id,
        wallet_scope=scope,
        amount=transaction.amount,
        direction=_value(transaction.direction),
        remark=transaction.remark,
        created_at=transaction.created_at.isoformat() if transaction.created_at else "",
    )


def get_account_or_404(session: Session, account_id: int) -> TaobaoAccount:
    account = session.get(TaobaoAccount, account_id)
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="淘宝账户不存在")
    return account


@router.post("/accounts", response_model=TaobaoAccountOut, status_code=status.HTTP_201_CREATED)
def create_account(request: TaobaoAccountCreate, db: Session = Depends(get_db)) -> TaobaoAccountOut:
    unsettled_wallet = create_wallet(
        db,
        name=f"{request.name} 未结算",
        wallet_type=WalletType.TAOBAO,
        currency=Currency.CNY,
    )
    settled_wallet = create_wallet(
        db,
        name=f"{request.name} 已结算",
        wallet_type=WalletType.TAOBAO,
        currency=Currency.CNY,
    )
    account = TaobaoAccount(
        name=request.name,
        unsettled_wallet_id=unsettled_wallet.id,
        settled_wallet_id=settled_wallet.id,
        remark=request.remark,
    )
    db.add(account)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="淘宝账户名称已存在") from exc
    db.refresh(account)
    return serialize_account(account)


@router.get("/accounts", response_model=list[TaobaoAccountOut])
def list_accounts(db: Session = Depends(get_db)) -> list[TaobaoAccountOut]:
    accounts = db.scalars(select(TaobaoAccount).order_by(TaobaoAccount.id)).all()
    return [serialize_account(account) for account in accounts]


@router.post(
    "/accounts/{account_id}/unsettled/credit",
    response_model=TaobaoTransactionOut,
    status_code=status.HTTP_201_CREATED,
)
def credit_unsettled(
    account_id: int,
    request: TaobaoMovementRequest,
    db: Session = Depends(get_db),
) -> TaobaoTransactionOut:
    account = get_account_or_404(db, account_id)
    transaction = credit(db, account.unsettled_wallet_id, request.amount, request.remark)
    db.commit()
    db.refresh(transaction)
    return serialize_transaction(account, transaction)


@router.post(
    "/accounts/{account_id}/settled/credit",
    response_model=TaobaoTransactionOut,
    status_code=status.HTTP_201_CREATED,
)
def credit_settled(
    account_id: int,
    request: TaobaoMovementRequest,
    db: Session = Depends(get_db),
) -> TaobaoTransactionOut:
    account = get_account_or_404(db, account_id)
    transaction = credit(db, account.settled_wallet_id, request.amount, request.remark)
    db.commit()
    db.refresh(transaction)
    return serialize_transaction(account, transaction)


@router.post(
    "/accounts/{account_id}/settled/debit",
    response_model=TaobaoTransactionOut,
    status_code=status.HTTP_201_CREATED,
)
def debit_settled(
    account_id: int,
    request: TaobaoMovementRequest,
    db: Session = Depends(get_db),
) -> TaobaoTransactionOut:
    account = get_account_or_404(db, account_id)
    try:
        transaction = debit(db, account.settled_wallet_id, request.amount, request.remark)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    db.refresh(transaction)
    return serialize_transaction(account, transaction)


@router.get("/accounts/{account_id}/transactions", response_model=list[TaobaoTransactionOut])
def list_transactions(account_id: int, db: Session = Depends(get_db)) -> list[TaobaoTransactionOut]:
    account = get_account_or_404(db, account_id)
    transactions = db.scalars(
        select(WalletTransaction)
        .where(WalletTransaction.wallet_id.in_([account.unsettled_wallet_id, account.settled_wallet_id]))
        .order_by(WalletTransaction.id)
    ).all()
    return [serialize_transaction(account, transaction) for transaction in transactions]
