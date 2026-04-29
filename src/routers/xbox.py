"""XBOX account API routes."""
from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.database import get_db
from src.models.xbox import (
    XboxAccount,
    XboxCountry,
    XboxCurrency,
    XboxTransaction,
    XboxTransactionType,
)


router = APIRouter(prefix="/xbox", tags=["xbox"])


COUNTRY_CURRENCY = {
    XboxCountry.US: XboxCurrency.USD,
    XboxCountry.UK: XboxCurrency.GBP,
}


class XboxAccountCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    country: XboxCountry
    remark: Optional[str] = None


class XboxAccountOut(BaseModel):
    id: int
    name: str
    country: str
    currency: str
    rmb_cost: Decimal
    local_balance: Decimal
    remark: Optional[str]
    created_at: str


class XboxRechargeRequest(BaseModel):
    rmb_amount: Decimal = Field(..., gt=0)
    local_amount: Decimal = Field(..., gt=0)
    remark: Optional[str] = None


class XboxConsumeRequest(BaseModel):
    local_amount: Decimal = Field(..., gt=0)
    remark: Optional[str] = None


class XboxTransactionOut(BaseModel):
    id: int
    account_id: int
    rmb_amount: Decimal
    local_amount: Decimal
    type: str
    remark: Optional[str]
    created_at: str


class XboxCurrencySummary(BaseModel):
    rmb_cost: Decimal
    local_balance: Decimal


class XboxSummaryOut(BaseModel):
    USD: XboxCurrencySummary
    GBP: XboxCurrencySummary


def _value(value):
    if isinstance(value, Enum):
        return value.value
    return value


def serialize_account(account: XboxAccount) -> XboxAccountOut:
    return XboxAccountOut(
        id=account.id,
        name=account.name,
        country=_value(account.country),
        currency=_value(account.currency),
        rmb_cost=account.rmb_cost,
        local_balance=account.local_balance,
        remark=account.remark,
        created_at=account.created_at.isoformat() if account.created_at else "",
    )


def serialize_transaction(transaction: XboxTransaction) -> XboxTransactionOut:
    return XboxTransactionOut(
        id=transaction.id,
        account_id=transaction.account_id,
        rmb_amount=transaction.rmb_amount,
        local_amount=transaction.local_amount,
        type=_value(transaction.type),
        remark=transaction.remark,
        created_at=transaction.created_at.isoformat() if transaction.created_at else "",
    )


def get_account_or_404(session: Session, account_id: int) -> XboxAccount:
    account = session.get(XboxAccount, account_id)
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="XBOX 账号不存在")
    return account


def apply_recharge_to_account(
    session: Session,
    account: XboxAccount,
    rmb_amount: Decimal,
    local_amount: Decimal,
    remark: Optional[str] = None,
) -> XboxTransaction:
    """累加 XBOX 账号 rmb_cost / local_balance 并写入一条 recharge 流水。

    仅 add + flush，不 commit；调用方负责事务边界，便于嵌入更大的原子操作。
    """
    account.rmb_cost = Decimal(account.rmb_cost) + Decimal(rmb_amount)
    account.local_balance = Decimal(account.local_balance) + Decimal(local_amount)
    transaction = XboxTransaction(
        account_id=account.id,
        rmb_amount=Decimal(rmb_amount),
        local_amount=Decimal(local_amount),
        type=XboxTransactionType.RECHARGE.value,
        remark=remark,
    )
    session.add(transaction)
    session.flush()
    return transaction


@router.post("/accounts", response_model=XboxAccountOut, status_code=status.HTTP_201_CREATED)
def create_account(request: XboxAccountCreate, db: Session = Depends(get_db)) -> XboxAccountOut:
    account = XboxAccount(
        name=request.name,
        country=request.country.value,
        currency=COUNTRY_CURRENCY[request.country].value,
        remark=request.remark,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return serialize_account(account)


@router.get("/accounts", response_model=list[XboxAccountOut])
def list_accounts(
    country: Optional[XboxCountry] = Query(None),
    db: Session = Depends(get_db),
) -> list[XboxAccountOut]:
    statement = select(XboxAccount).order_by(XboxAccount.id)
    if country is not None:
        statement = statement.where(XboxAccount.country == country.value)
    accounts = db.scalars(statement).all()
    return [serialize_account(account) for account in accounts]


@router.post(
    "/accounts/{account_id}/recharge",
    response_model=XboxTransactionOut,
    status_code=status.HTTP_201_CREATED,
)
def recharge_account(
    account_id: int,
    request: XboxRechargeRequest,
    db: Session = Depends(get_db),
) -> XboxTransactionOut:
    account = get_account_or_404(db, account_id)
    transaction = apply_recharge_to_account(
        db,
        account,
        rmb_amount=request.rmb_amount,
        local_amount=request.local_amount,
        remark=request.remark,
    )
    db.commit()
    db.refresh(transaction)
    return serialize_transaction(transaction)


@router.post(
    "/accounts/{account_id}/consume",
    response_model=XboxTransactionOut,
    status_code=status.HTTP_201_CREATED,
)
def consume_account(
    account_id: int,
    request: XboxConsumeRequest,
    db: Session = Depends(get_db),
) -> XboxTransactionOut:
    account = get_account_or_404(db, account_id)
    if Decimal(account.local_balance) < request.local_amount:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当地币余额不足")
    account.local_balance = Decimal(account.local_balance) - request.local_amount
    transaction = XboxTransaction(
        account_id=account.id,
        rmb_amount=Decimal("0"),
        local_amount=request.local_amount,
        type=XboxTransactionType.CONSUME.value,
        remark=request.remark,
    )
    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    return serialize_transaction(transaction)


@router.get("/accounts/{account_id}/transactions", response_model=list[XboxTransactionOut])
def list_account_transactions(
    account_id: int,
    db: Session = Depends(get_db),
) -> list[XboxTransactionOut]:
    get_account_or_404(db, account_id)
    transactions = db.scalars(
        select(XboxTransaction)
        .where(XboxTransaction.account_id == account_id)
        .order_by(XboxTransaction.id)
    ).all()
    return [serialize_transaction(transaction) for transaction in transactions]


@router.get("/summary", response_model=XboxSummaryOut)
def xbox_summary(db: Session = Depends(get_db)) -> XboxSummaryOut:
    rows = db.execute(
        select(
            XboxAccount.currency,
            func.coalesce(func.sum(XboxAccount.rmb_cost), 0),
            func.coalesce(func.sum(XboxAccount.local_balance), 0),
        ).group_by(XboxAccount.currency)
    ).all()
    totals = {
        currency: XboxCurrencySummary(
            rmb_cost=Decimal(str(rmb_cost)),
            local_balance=Decimal(str(local_balance)),
        )
        for currency, rmb_cost, local_balance in rows
    }
    empty = XboxCurrencySummary(rmb_cost=Decimal("0"), local_balance=Decimal("0"))
    return XboxSummaryOut(
        USD=totals.get(XboxCurrency.USD.value, empty),
        GBP=totals.get(XboxCurrency.GBP.value, empty),
    )
