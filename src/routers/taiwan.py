"""Taiwan TWD wallet API routes."""
from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
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
    # CEO 2026-05-17: 台湾钱包改为 group + 子钱包结构, 前端要这 3 个字段渲染层级
    is_group: bool = False
    parent_id: Optional[int] = None
    remark: Optional[str] = None


class TaiwanMovementRequest(BaseModel):
    amount: Decimal = Field(..., gt=0)
    remark: Optional[str] = None
    # CEO 2026-05-18: 流水追溯, 前端从 localStorage 传操作人名字
    operator_name: Optional[str] = None


class TaiwanTransactionOut(BaseModel):
    id: int
    wallet_id: int
    amount: Decimal
    direction: str
    remark: Optional[str]
    created_at: str
    operator_name: Optional[str] = None


# CEO 2026-05-18: 新增 / 编辑子钱包请求体
class TaiwanWalletCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    parent_id: int = Field(..., description="必须属于一个 group 父钱包")
    remark: Optional[str] = None


class TaiwanWalletUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    remark: Optional[str] = None


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
        is_group=bool(wallet.is_group),
        parent_id=wallet.parent_id,
        remark=wallet.remark,
    )


def serialize_transaction(transaction: WalletTransaction) -> TaiwanTransactionOut:
    return TaiwanTransactionOut(
        id=transaction.id,
        wallet_id=transaction.wallet_id,
        amount=transaction.amount,
        direction=_value(transaction.direction),
        remark=transaction.remark,
        created_at=transaction.created_at.isoformat() if transaction.created_at else "",
        operator_name=getattr(transaction, "operator_name", None),
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
    wallet = get_taiwan_wallet_or_404(db, wallet_id)
    # CEO 2026-05-18: group 父钱包不应该直接收/支, 只能在子钱包操作
    if wallet.is_group:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="父钱包不能直接收支, 请在子钱包操作")
    transaction = credit(db, wallet_id, request.amount, request.remark, operator_name=request.operator_name)
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
    wallet = get_taiwan_wallet_or_404(db, wallet_id)
    if wallet.is_group:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="父钱包不能直接收支, 请在子钱包操作")
    try:
        transaction = debit(db, wallet_id, request.amount, request.remark, operator_name=request.operator_name)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    db.refresh(transaction)
    return serialize_transaction(transaction)


# CEO 2026-05-18: 新增子钱包 + 编辑钱包
@router.post(
    "/wallets",
    response_model=TaiwanWalletOut,
    status_code=status.HTTP_201_CREATED,
)
def create_taiwan_wallet(
    request: TaiwanWalletCreateRequest,
    db: Session = Depends(get_db),
) -> TaiwanWalletOut:
    """新增一个台湾子钱包(必须挂到某个 group 父钱包下)。"""
    from src.models.wallet import Currency, WalletType, create_wallet

    parent = db.get(Wallet, request.parent_id)
    if parent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="父钱包不存在")
    if not parent.is_group:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="父钱包必须是 group 类型")
    if not is_taiwan_wallet(parent):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="父钱包不是台湾 TWD 钱包")
    wallet = create_wallet(
        db,
        name=request.name,
        wallet_type=WalletType.TAIWAN,
        currency=Currency.TWD,
        parent_id=request.parent_id,
        is_group=False,
        remark=request.remark,
    )
    db.commit()
    db.refresh(wallet)
    return serialize_wallet(wallet)


@router.patch(
    "/wallets/{wallet_id}",
    response_model=TaiwanWalletOut,
)
def update_taiwan_wallet(
    wallet_id: int,
    request: TaiwanWalletUpdateRequest,
    db: Session = Depends(get_db),
) -> TaiwanWalletOut:
    """编辑台湾钱包的 name / remark (改卡号 / 注册人)。"""
    wallet = get_taiwan_wallet_or_404(db, wallet_id)
    if request.name is not None:
        wallet.name = request.name
    if request.remark is not None:
        wallet.remark = request.remark if request.remark.strip() else None
    db.commit()
    db.refresh(wallet)
    return serialize_wallet(wallet)


@router.delete("/wallets/{wallet_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_taiwan_wallet(wallet_id: int, db: Session = Depends(get_db)) -> Response:
    """软删除一个子钱包(只能删子钱包, 不能删 group)。"""
    wallet = get_taiwan_wallet_or_404(db, wallet_id)
    if wallet.is_group:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="不能删除 group 父钱包")
    if Decimal(wallet.balance) != Decimal("0"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="余额不为 0, 不能删除")
    from src.utils.time import china_now
    wallet.deleted_at = china_now()
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/wallets/{wallet_id}/transactions", response_model=list[TaiwanTransactionOut])
def get_transactions(wallet_id: int, db: Session = Depends(get_db)) -> list[TaiwanTransactionOut]:
    get_taiwan_wallet_or_404(db, wallet_id)
    return [serialize_transaction(transaction) for transaction in list_transactions(db, wallet_id)]


@router.get("/summary", response_model=TaiwanSummaryOut)
def get_summary(db: Session = Depends(get_db)) -> TaiwanSummaryOut:
    # CEO 2026-05-17: 改了结构后, "合计" 只算叶子钱包(子钱包), 不重复算 group;
    # "钱包数" 也只算叶子(group 不算独立钱包). 同时过滤软删除.
    total = db.scalar(
        select(func.coalesce(func.sum(Wallet.balance), 0)).where(
            Wallet.type == "TAIWAN",
            Wallet.currency == "TWD",
            Wallet.is_group.is_(False),
            Wallet.deleted_at.is_(None),
        )
    )
    wallet_count = db.scalar(
        select(func.count()).select_from(Wallet).where(
            Wallet.type == "TAIWAN",
            Wallet.currency == "TWD",
            Wallet.is_group.is_(False),
            Wallet.deleted_at.is_(None),
        )
    )
    return TaiwanSummaryOut(total_balance=Decimal(str(total)), wallet_count=int(wallet_count or 0))
