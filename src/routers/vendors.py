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
from src.models.wallet import Wallet
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
