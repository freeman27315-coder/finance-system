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
    Currency,
    TransactionDirection,
    Wallet,
    WalletTransaction,
    WalletType,
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


class PaymentRequest(BaseModel):
    from_wallet_id: int
    amount: Decimal
    exchange_rate: Optional[Decimal] = None
    remark: Optional[str] = Field(None, max_length=500)


class PaymentTransactionOut(BaseModel):
    id: int
    wallet_id: int
    amount: Decimal
    direction: str
    remark: Optional[str]
    created_at: str


class PaymentOut(BaseModel):
    from_transaction: PaymentTransactionOut
    vendor_transaction: PaymentTransactionOut
    exchange_rate: Decimal
    from_wallet_balance: Decimal
    vendor_wallet_balance: Decimal


def _currency_value(wallet: Wallet) -> str:
    return wallet.currency.value if isinstance(wallet.currency, Currency) else wallet.currency


def _type_value(wallet: Wallet) -> str:
    return wallet.type.value if isinstance(wallet.type, WalletType) else wallet.type


def _serialize_payment_tx(tx: WalletTransaction) -> PaymentTransactionOut:
    direction = (
        tx.direction.value
        if isinstance(tx.direction, TransactionDirection)
        else tx.direction
    )
    return PaymentTransactionOut(
        id=tx.id,
        wallet_id=tx.wallet_id,
        amount=Decimal(tx.amount),
        direction=direction,
        remark=tx.remark,
        created_at=tx.created_at.isoformat() if tx.created_at else "",
    )


_ASSET_TYPES = {WalletType.ASSET_RMB.value, WalletType.ASSET_USDT.value}


@router.post("/{vendor_id}/payment", response_model=PaymentOut)
def pay_vendor(
    vendor_id: int,
    request: PaymentRequest,
    db: Session = Depends(get_db),
) -> PaymentOut:
    # 1. vendor 不存在
    vendor = _get_vendor_or_404(db, vendor_id)

    # 2. from 钱包不存在
    from_wallet = db.get(Wallet, request.from_wallet_id)
    if from_wallet is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="源钱包不存在")

    # 3. from 必须是资产钱包
    if _type_value(from_wallet) not in _ASSET_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="只能从资产钱包付款",
        )

    # 4. from 已软删
    if from_wallet.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="钱包已删除")

    # 5. from 是分组
    if from_wallet.is_group:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="分组钱包不可作为付款源",
        )

    # 6. vendor wallet 兜底
    vendor_wallet = db.get(Wallet, vendor.wallet_id)
    if vendor_wallet is None or vendor_wallet.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="供应商钱包不可用",
        )

    # 7. amount <= 0
    amount = Decimal(str(request.amount))
    if amount <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="金额必须大于 0")

    from_currency = _currency_value(from_wallet)
    vendor_currency = _currency_value(vendor_wallet)

    # 8/9. 跨币种汇率必填，同币种忽略
    if from_currency != vendor_currency:
        if request.exchange_rate is None or Decimal(str(request.exchange_rate)) <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="跨币种付款必须提供汇率",
            )
        rate = Decimal(str(request.exchange_rate))
    else:
        rate = Decimal("1")

    vendor_amount = amount * rate

    user_remark = request.remark or ""
    suffix_from = f"付款→{vendor.name} {vendor_amount} {vendor_currency}"
    suffix_vendor = f"←{from_wallet.name} 付款 {amount} {from_currency}"
    from_remark = f"{user_remark} {suffix_from}".strip() if user_remark else suffix_from
    vendor_remark = f"{user_remark} {suffix_vendor}".strip() if user_remark else suffix_vendor

    # 10/11. 原子事务：双 debit
    try:
        from_tx = debit(db, from_wallet.id, amount, from_remark)
        vendor_tx = debit(db, vendor_wallet.id, vendor_amount, vendor_remark)
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise

    db.refresh(from_tx)
    db.refresh(vendor_tx)
    db.refresh(from_wallet)
    db.refresh(vendor_wallet)

    return PaymentOut(
        from_transaction=_serialize_payment_tx(from_tx),
        vendor_transaction=_serialize_payment_tx(vendor_tx),
        exchange_rate=rate,
        from_wallet_balance=Decimal(from_wallet.balance),
        vendor_wallet_balance=Decimal(vendor_wallet.balance),
    )


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
