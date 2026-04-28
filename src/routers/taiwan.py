"""Taiwan TWD wallet API routes."""
from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.database import get_db
from src.models.wallet import Wallet, WalletTransaction, credit, debit, list_transactions
from src.services.taiwan import is_taiwan_wallet, list_taiwan_wallets


router = APIRouter(prefix="/taiwan", tags=["taiwan"])


class TaiwanWalletOut(BaseModel):
    id: int
    name: str
    type: str
    currency: str
    balance: Decimal
    created_at: str


class TaiwanMovementRequest(BaseModel):
    amount: Decimal = Field(..., gt=0)
    remark: Optional[str] = None


class TaiwanTransactionOut(BaseModel):
    id: int
    wallet_id: int
    amount: Decimal
    direction: str
    remark: Optional[str]
    created_at: str


class TaiwanSummaryOut(BaseModel):
    total_balance: Decimal
    wallet_count: int


def _value(value):
    if isinstance(value, Enum):
        return value.value
    return value


def serialize_wallet(wallet: Wallet) -> TaiwanWalletOut:
    return TaiwanWalletOut(
        id=wallet.id,
        name=wallet.name,
        type=_value(wallet.type),
        currency=_value(wallet.currency),
        balance=wallet.balance,
        created_at=wallet.created_at.isoformat() if wallet.created_at else "",
    )


def serialize_transaction(transaction: WalletTransaction) -> TaiwanTransactionOut:
    return TaiwanTransactionOut(
        id=transaction.id,
        wallet_id=transaction.wallet_id,
        amount=transaction.amount,
        direction=_value(transaction.direction),
        remark=transaction.remark,
        created_at=transaction.created_at.isoformat() if transaction.created_at else "",
    )


def get_taiwan_wallet_or_404(session: Session, wallet_id: int) -> Wallet:
    wallet = session.get(Wallet, wallet_id)
    if wallet is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="台湾钱包不存在")
    if not is_taiwan_wallet(wallet):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该钱包不是台湾 TWD 钱包")
    return wallet


@router.get("/wallets", response_model=list[TaiwanWalletOut])
def get_wallets(db: Session = Depends(get_db)) -> list[TaiwanWalletOut]:
    return [serialize_wallet(wallet) for wallet in list_taiwan_wallets(db)]


@router.post(
    "/wallets/{wallet_id}/credit",
    response_model=TaiwanTransactionOut,
    status_code=status.HTTP_201_CREATED,
)
def credit_wallet(
    wallet_id: int,
    request: TaiwanMovementRequest,
    db: Session = Depends(get_db),
) -> TaiwanTransactionOut:
    get_taiwan_wallet_or_404(db, wallet_id)
    transaction = credit(db, wallet_id, request.amount, request.remark)
    db.commit()
    db.refresh(transaction)
    return serialize_transaction(transaction)


@router.post(
    "/wallets/{wallet_id}/debit",
    response_model=TaiwanTransactionOut,
    status_code=status.HTTP_201_CREATED,
)
def debit_wallet(
    wallet_id: int,
    request: TaiwanMovementRequest,
    db: Session = Depends(get_db),
) -> TaiwanTransactionOut:
    get_taiwan_wallet_or_404(db, wallet_id)
    try:
        transaction = debit(db, wallet_id, request.amount, request.remark)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    db.refresh(transaction)
    return serialize_transaction(transaction)


@router.get("/wallets/{wallet_id}/transactions", response_model=list[TaiwanTransactionOut])
def get_transactions(wallet_id: int, db: Session = Depends(get_db)) -> list[TaiwanTransactionOut]:
    get_taiwan_wallet_or_404(db, wallet_id)
    return [serialize_transaction(transaction) for transaction in list_transactions(db, wallet_id)]


@router.get("/summary", response_model=TaiwanSummaryOut)
def get_summary(db: Session = Depends(get_db)) -> TaiwanSummaryOut:
    total = db.scalar(
        select(func.coalesce(func.sum(Wallet.balance), 0)).where(
            Wallet.type == "TAIWAN",
            Wallet.currency == "TWD",
        )
    )
    wallet_count = db.scalar(
        select(func.count()).select_from(Wallet).where(
            Wallet.type == "TAIWAN",
            Wallet.currency == "TWD",
        )
    )
    return TaiwanSummaryOut(total_balance=Decimal(str(total)), wallet_count=int(wallet_count or 0))
