"""Asset wallet API routes."""
from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.database import get_db
from src.models.wallet import Wallet, credit, debit, list_transactions
from src.services.assets import create_asset_sub_wallet, is_asset_wallet, list_asset_wallets


router = APIRouter(prefix="/wallets/assets", tags=["asset-wallets"])


class SubWalletCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    is_group: bool = False


class WalletMovementRequest(BaseModel):
    amount: Decimal = Field(..., gt=0)
    remark: Optional[str] = Field(None, max_length=500)


class WalletOut(BaseModel):
    id: int
    name: str
    type: str
    currency: str
    balance: Decimal
    is_group: bool
    parent_id: Optional[int]
    created_at: str
    children: list["WalletOut"] = Field(default_factory=list)


class TransactionOut(BaseModel):
    id: int
    wallet_id: int
    amount: Decimal
    direction: str
    remark: Optional[str]
    created_at: str


def _value(value):
    if isinstance(value, Enum):
        return value.value
    return value


def _computed_balance(wallet: Wallet, children_by_parent: dict[int, list[Wallet]]) -> Decimal:
    if not wallet.is_group:
        return wallet.balance
    return sum(
        (_computed_balance(child, children_by_parent) for child in children_by_parent.get(wallet.id, [])),
        Decimal("0"),
    )


def serialize_wallet(wallet: Wallet, children_by_parent: dict[int, list[Wallet]] | None = None) -> WalletOut:
    child_wallets = children_by_parent.get(wallet.id, []) if children_by_parent is not None else []
    return WalletOut(
        id=wallet.id,
        name=wallet.name,
        type=_value(wallet.type),
        currency=_value(wallet.currency),
        balance=_computed_balance(wallet, children_by_parent) if children_by_parent is not None else wallet.balance,
        is_group=bool(wallet.is_group),
        parent_id=wallet.parent_id,
        created_at=wallet.created_at.isoformat() if wallet.created_at else "",
        children=[serialize_wallet(child, children_by_parent) for child in child_wallets],
    )


def serialize_transaction(transaction) -> TransactionOut:
    return TransactionOut(
        id=transaction.id,
        wallet_id=transaction.wallet_id,
        amount=transaction.amount,
        direction=_value(transaction.direction),
        remark=transaction.remark,
        created_at=transaction.created_at.isoformat() if transaction.created_at else "",
    )


def get_asset_wallet_or_404(session: Session, wallet_id: int) -> Wallet:
    wallet = session.get(Wallet, wallet_id)
    if wallet is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资产钱包不存在")
    if not is_asset_wallet(wallet):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="该钱包不是资产钱包")
    return wallet


def get_postable_asset_wallet_or_404(session: Session, wallet_id: int) -> Wallet:
    wallet = get_asset_wallet_or_404(session, wallet_id)
    if wallet.is_group:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="分组钱包不可直接记账，请操作叶子钱包",
        )
    return wallet


@router.get("", response_model=list[WalletOut])
def list_assets(db: Session = Depends(get_db)) -> list[WalletOut]:
    wallets = list_asset_wallets(db)
    children_by_parent: dict[int, list[Wallet]] = {}
    roots: list[Wallet] = []

    for wallet in wallets:
        if wallet.parent_id is None:
            roots.append(wallet)
        else:
            children_by_parent.setdefault(wallet.parent_id, []).append(wallet)

    return [serialize_wallet(root, children_by_parent) for root in roots]


@router.post("/{wallet_id}/sub", response_model=WalletOut, status_code=status.HTTP_201_CREATED)
def create_sub_wallet(
    wallet_id: int,
    request: SubWalletCreate,
    db: Session = Depends(get_db),
) -> WalletOut:
    parent = get_asset_wallet_or_404(db, wallet_id)
    sub_wallet = create_asset_sub_wallet(db, parent, request.name, is_group=request.is_group)
    db.commit()
    db.refresh(sub_wallet)
    return serialize_wallet(sub_wallet)


@router.post("/{wallet_id}/credit", response_model=TransactionOut, status_code=status.HTTP_201_CREATED)
def credit_asset_wallet(
    wallet_id: int,
    request: WalletMovementRequest,
    db: Session = Depends(get_db),
) -> TransactionOut:
    get_postable_asset_wallet_or_404(db, wallet_id)
    transaction = credit(db, wallet_id, request.amount, request.remark)
    db.commit()
    db.refresh(transaction)
    return serialize_transaction(transaction)


@router.post("/{wallet_id}/debit", response_model=TransactionOut, status_code=status.HTTP_201_CREATED)
def debit_asset_wallet(
    wallet_id: int,
    request: WalletMovementRequest,
    db: Session = Depends(get_db),
) -> TransactionOut:
    get_postable_asset_wallet_or_404(db, wallet_id)
    try:
        transaction = debit(db, wallet_id, request.amount, request.remark)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    db.refresh(transaction)
    return serialize_transaction(transaction)


@router.get("/{wallet_id}/transactions", response_model=list[TransactionOut])
def get_asset_wallet_transactions(
    wallet_id: int,
    db: Session = Depends(get_db),
) -> list[TransactionOut]:
    get_asset_wallet_or_404(db, wallet_id)
    return [serialize_transaction(transaction) for transaction in list_transactions(db, wallet_id)]
