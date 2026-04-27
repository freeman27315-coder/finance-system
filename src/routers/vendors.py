"""Vendor payable and receivable API routes."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.database import get_db
from src.models.vendor import Vendor, VendorBill, VendorBillDirection, VendorBillStatus


router = APIRouter(prefix="/vendors", tags=["vendors"])


class VendorCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    remark: Optional[str] = None


class VendorOut(BaseModel):
    id: int
    name: str
    remark: Optional[str]
    created_at: str


class VendorBillCreate(BaseModel):
    direction: VendorBillDirection
    amount: Decimal = Field(..., gt=0)
    due_date: Optional[date] = None
    remark: Optional[str] = None


class VendorBillOut(BaseModel):
    id: int
    vendor_id: int
    direction: str
    amount: Decimal
    status: str
    due_date: Optional[str]
    remark: Optional[str]
    created_at: str


class VendorSummaryOut(BaseModel):
    payable: Decimal
    receivable: Decimal
    net: Decimal


def _value(value):
    if isinstance(value, Enum):
        return value.value
    return value


def serialize_vendor(vendor: Vendor) -> VendorOut:
    return VendorOut(
        id=vendor.id,
        name=vendor.name,
        remark=vendor.remark,
        created_at=vendor.created_at.isoformat() if vendor.created_at else "",
    )


def serialize_bill(bill: VendorBill) -> VendorBillOut:
    return VendorBillOut(
        id=bill.id,
        vendor_id=bill.vendor_id,
        direction=_value(bill.direction),
        amount=bill.amount,
        status=_value(bill.status),
        due_date=bill.due_date.isoformat() if bill.due_date else None,
        remark=bill.remark,
        created_at=bill.created_at.isoformat() if bill.created_at else "",
    )


def get_vendor_or_404(session: Session, vendor_id: int) -> Vendor:
    vendor = session.get(Vendor, vendor_id)
    if vendor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="供应商不存在")
    return vendor


@router.post("", response_model=VendorOut, status_code=status.HTTP_201_CREATED)
def create_vendor(request: VendorCreate, db: Session = Depends(get_db)) -> VendorOut:
    vendor = Vendor(name=request.name, remark=request.remark)
    db.add(vendor)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="供应商名称已存在") from exc
    db.refresh(vendor)
    return serialize_vendor(vendor)


@router.get("", response_model=list[VendorOut])
def list_vendors(db: Session = Depends(get_db)) -> list[VendorOut]:
    vendors = db.scalars(select(Vendor).order_by(Vendor.id)).all()
    return [serialize_vendor(vendor) for vendor in vendors]


@router.post("/{vendor_id}/bills", response_model=VendorBillOut, status_code=status.HTTP_201_CREATED)
def create_vendor_bill(
    vendor_id: int,
    request: VendorBillCreate,
    db: Session = Depends(get_db),
) -> VendorBillOut:
    get_vendor_or_404(db, vendor_id)
    bill = VendorBill(
        vendor_id=vendor_id,
        direction=request.direction.value,
        amount=request.amount,
        due_date=request.due_date,
        remark=request.remark,
    )
    db.add(bill)
    db.commit()
    db.refresh(bill)
    return serialize_bill(bill)


@router.get("/{vendor_id}/bills", response_model=list[VendorBillOut])
def list_vendor_bills(vendor_id: int, db: Session = Depends(get_db)) -> list[VendorBillOut]:
    get_vendor_or_404(db, vendor_id)
    bills = db.scalars(
        select(VendorBill).where(VendorBill.vendor_id == vendor_id).order_by(VendorBill.id)
    ).all()
    return [serialize_bill(bill) for bill in bills]


@router.patch("/bills/{bill_id}/settle", response_model=VendorBillOut)
def settle_vendor_bill(bill_id: int, db: Session = Depends(get_db)) -> VendorBillOut:
    bill = db.get(VendorBill, bill_id)
    if bill is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账单不存在")
    bill.status = VendorBillStatus.SETTLED.value
    db.commit()
    db.refresh(bill)
    return serialize_bill(bill)


@router.get("/summary", response_model=VendorSummaryOut)
def vendor_summary(db: Session = Depends(get_db)) -> VendorSummaryOut:
    rows = db.execute(
        select(VendorBill.direction, func.coalesce(func.sum(VendorBill.amount), 0))
        .where(VendorBill.status == VendorBillStatus.PENDING.value)
        .group_by(VendorBill.direction)
    ).all()
    totals = {direction: Decimal(str(amount)) for direction, amount in rows}
    payable = totals.get(VendorBillDirection.PAYABLE.value, Decimal("0"))
    receivable = totals.get(VendorBillDirection.RECEIVABLE.value, Decimal("0"))
    return VendorSummaryOut(payable=payable, receivable=receivable, net=receivable - payable)
