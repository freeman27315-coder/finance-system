"""Vendor API routes (wallet-backed)."""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.database import get_db
from src.models.vendor import Vendor
from src.models.wallet import (
    TransactionDirection,
    Wallet,
    WalletTransaction,
    credit,
    debit,
)
from src.services.vendors import create_vendor_wallet


router = APIRouter(prefix="/vendors", tags=["vendors"])


class VendorCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    remark: Optional[str] = None


class VendorOut(BaseModel):
    id: int
    name: str
    remark: Optional[str]
    walletId: int
    balance: Decimal
    created_at: str


def serialize_vendor(vendor: Vendor, wallet: Wallet) -> VendorOut:
    return VendorOut(
        id=vendor.id,
        name=vendor.name,
        remark=vendor.remark,
        walletId=wallet.id,
        balance=Decimal(wallet.balance),
        created_at=vendor.created_at.isoformat() if vendor.created_at else "",
    )


@router.post("", response_model=VendorOut, status_code=status.HTTP_201_CREATED)
def create_vendor(request: VendorCreate, db: Session = Depends(get_db)) -> VendorOut:
    wallet = create_vendor_wallet(db, request.name)
    vendor = Vendor(name=request.name, remark=request.remark, wallet_id=wallet.id)
    db.add(vendor)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="供应商名称已存在") from exc
    db.refresh(vendor)
    db.refresh(wallet)
    return serialize_vendor(vendor, wallet)


@router.get("", response_model=list[VendorOut])
def list_vendors(db: Session = Depends(get_db)) -> list[VendorOut]:
    rows = db.execute(
        select(Vendor, Wallet).join(Wallet, Vendor.wallet_id == Wallet.id).order_by(Vendor.id)
    ).all()
    return [serialize_vendor(vendor, wallet) for vendor, wallet in rows]


class VendorAdjustRequest(BaseModel):
    amount: Decimal
    remark: Optional[str] = None


class VendorTransactionOut(BaseModel):
    id: int
    walletId: int
    amount: Decimal
    direction: str  # "in" / "out"
    remark: Optional[str]
    createdAt: str


def _get_vendor_or_404(db: Session, vendor_id: int) -> Vendor:
    vendor = db.get(Vendor, vendor_id)
    if vendor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="供应商不存在")
    return vendor


@router.post("/{vendor_id}/adjust", response_model=VendorOut)
def adjust_vendor(
    vendor_id: int,
    request: VendorAdjustRequest,
    db: Session = Depends(get_db),
) -> VendorOut:
    if request.amount == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="调整金额不能为 0",
        )
    vendor = _get_vendor_or_404(db, vendor_id)

    if request.amount > 0:
        credit(db, vendor.wallet_id, request.amount, request.remark)
    else:
        debit(db, vendor.wallet_id, abs(request.amount), request.remark)

    db.commit()
    db.refresh(vendor)
    wallet = db.get(Wallet, vendor.wallet_id)
    return serialize_vendor(vendor, wallet)


@router.get("/{vendor_id}/transactions", response_model=list[VendorTransactionOut])
def list_vendor_transactions(
    vendor_id: int,
    db: Session = Depends(get_db),
) -> list[VendorTransactionOut]:
    vendor = _get_vendor_or_404(db, vendor_id)
    txs = db.scalars(
        select(WalletTransaction)
        .where(WalletTransaction.wallet_id == vendor.wallet_id)
        .order_by(WalletTransaction.created_at.desc(), WalletTransaction.id.desc())
    ).all()
    result: list[VendorTransactionOut] = []
    for tx in txs:
        direction = (
            tx.direction.value
            if isinstance(tx.direction, TransactionDirection)
            else tx.direction
        )
        result.append(
            VendorTransactionOut(
                id=tx.id,
                walletId=tx.wallet_id,
                amount=Decimal(tx.amount),
                direction=direction,
                remark=tx.remark,
                createdAt=tx.created_at.isoformat() if tx.created_at else "",
            )
        )
    return result
