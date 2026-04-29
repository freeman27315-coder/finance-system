"""Wallet-to-wallet transfer API routes."""
from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.database import get_db
from src.models.wallet import Currency, Wallet, WalletType, credit, debit


router = APIRouter(prefix="/wallets", tags=["transfers"])


class TransferRequest(BaseModel):
    from_wallet_id: int
    to_wallet_id: int
    amount: Decimal
    exchange_rate: Optional[Decimal] = None
    remark: Optional[str] = Field(None, max_length=500)


class TransactionOut(BaseModel):
    id: int
    wallet_id: int
    amount: Decimal
    direction: str
    remark: Optional[str]
    created_at: str


class TransferOut(BaseModel):
    from_: TransactionOut = Field(..., alias="from")
    to: TransactionOut
    exchange_rate: Decimal
    from_wallet_balance: Decimal
    to_wallet_balance: Decimal

    model_config = {"populate_by_name": True}


def _value(value):
    if isinstance(value, Enum):
        return value.value
    return value


def _serialize_transaction(transaction) -> TransactionOut:
    return TransactionOut(
        id=transaction.id,
        wallet_id=transaction.wallet_id,
        amount=Decimal(transaction.amount),
        direction=_value(transaction.direction),
        remark=transaction.remark,
        created_at=transaction.created_at.isoformat() if transaction.created_at else "",
    )


def _currency_value(wallet: Wallet) -> str:
    return wallet.currency.value if isinstance(wallet.currency, Currency) else wallet.currency


def _type_value(wallet: Wallet) -> str:
    return wallet.type.value if isinstance(wallet.type, WalletType) else wallet.type


@router.post("/transfer", response_model=TransferOut, response_model_by_alias=True)
def transfer_between_wallets(
    request: TransferRequest,
    db: Session = Depends(get_db),
) -> TransferOut:
    # 1. from 钱包不存在
    from_wallet = db.get(Wallet, request.from_wallet_id)
    if from_wallet is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="源钱包不存在")

    # 2. to 钱包不存在
    to_wallet = db.get(Wallet, request.to_wallet_id)
    if to_wallet is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="目标钱包不存在")

    # 3. 不能转账给自己
    if request.from_wallet_id == request.to_wallet_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能转账给自己")

    # 4. from 已软删
    if from_wallet.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="源钱包已删除")

    # 5. to 已软删
    if to_wallet.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="目标钱包已删除")

    # 6. from 是分组
    if from_wallet.is_group:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="分组钱包不可作为转出钱包",
        )

    # 7. to 是分组
    if to_wallet.is_group:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="分组钱包不可作为转入钱包",
        )

    # 8. amount <= 0
    amount = Decimal(str(request.amount))
    if amount <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="金额必须大于 0")

    from_currency = _currency_value(from_wallet)
    to_currency = _currency_value(to_wallet)

    # 9 / 10. 跨币种汇率必填，同币种忽略前端汇率
    if from_currency != to_currency:
        if request.exchange_rate is None or Decimal(str(request.exchange_rate)) <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="跨币种转账必须提供汇率",
            )
        rate = Decimal(str(request.exchange_rate))
    else:
        rate = Decimal("1")

    to_amount = amount * rate

    # 备注组装
    user_remark = request.remark or ""
    suffix_from = f"→{to_wallet.name} {to_amount} {to_currency}"
    suffix_to = f"←{from_wallet.name} {amount} {from_currency}"
    debit_remark = f"{user_remark} {suffix_from}".strip() if user_remark else suffix_from
    credit_remark = f"{user_remark} {suffix_to}".strip() if user_remark else suffix_to

    # 11. 原子事务：debit + credit；任何一步失败回滚
    try:
        debit_tx = debit(db, from_wallet.id, amount, debit_remark)
        credit_tx = credit(db, to_wallet.id, to_amount, credit_remark)
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise

    db.refresh(debit_tx)
    db.refresh(credit_tx)
    db.refresh(from_wallet)
    db.refresh(to_wallet)

    return TransferOut(
        **{"from": _serialize_transaction(debit_tx)},
        to=_serialize_transaction(credit_tx),
        exchange_rate=rate,
        from_wallet_balance=Decimal(from_wallet.balance),
        to_wallet_balance=Decimal(to_wallet.balance),
    )
