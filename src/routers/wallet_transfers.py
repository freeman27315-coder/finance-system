"""划转单 (钱包间转账) HTTP 路由.

Issue #129: 一笔划转 = 两条 wallet_transactions(OUT + IN), 用 transfer_id 绑死,
锁汇率快照. 典型场景: 台湾 TWD → 资产 USDT 归集.

端点:
- POST   /api/wallet-transfers       创建划转
- GET    /api/wallet-transfers       列表 + 筛选
- GET    /api/wallet-transfers/{id}  详情(含两条流水引用)
- DELETE /api/wallet-transfers/{id}  撤销(反向冲销 + 软删)
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.database import get_db
from src.models.wallet import Wallet, WalletTransfer
from src.services.wallet_transfer import (
    cancel_transfer,
    create_transfer,
    find_transfer_transactions,
    get_transfer,
    list_transfers,
)


router = APIRouter()


# -------- Pydantic 模型 --------


class WalletTransferCreateRequest(BaseModel):
    from_wallet_id: int = Field(..., gt=0)
    to_wallet_id: int = Field(..., gt=0)
    from_amount: Decimal = Field(..., gt=0, description="出账金额, 正数")
    to_amount: Decimal = Field(..., gt=0, description="入账金额, 正数")
    business_date: Optional[date] = None
    operator_name: Optional[str] = Field(None, max_length=120)
    note: Optional[str] = None


class TransferTransactionRef(BaseModel):
    """划转关联的流水简要引用(详情接口里返回 2 条)."""

    id: int
    wallet_id: int
    direction: str
    amount: Decimal
    remark: Optional[str] = None


class WalletTransferOut(BaseModel):
    id: int
    from_wallet_id: int
    to_wallet_id: int
    from_wallet_name: Optional[str] = None
    to_wallet_name: Optional[str] = None
    from_amount: Decimal
    to_amount: Decimal
    rate: Decimal
    from_currency: str
    to_currency: str
    business_date: Optional[date] = None
    operator_name: Optional[str] = None
    note: Optional[str] = None
    created_at: str
    deleted_at: Optional[str] = None
    transactions: list[TransferTransactionRef] = []


def _serialize_transfer(
    session: Session, transfer: WalletTransfer, include_tx: bool = True
) -> WalletTransferOut:
    """序列化划转单. include_tx=True 时附带关联流水(详情接口用)."""
    from_wallet = session.get(Wallet, transfer.from_wallet_id)
    to_wallet = session.get(Wallet, transfer.to_wallet_id)

    tx_refs: list[TransferTransactionRef] = []
    if include_tx:
        for tx in find_transfer_transactions(session, transfer.id):
            direction = tx.direction.value if hasattr(tx.direction, "value") else tx.direction
            tx_refs.append(
                TransferTransactionRef(
                    id=tx.id,
                    wallet_id=tx.wallet_id,
                    direction=direction,
                    amount=Decimal(tx.amount),
                    remark=tx.remark,
                )
            )

    return WalletTransferOut(
        id=transfer.id,
        from_wallet_id=transfer.from_wallet_id,
        to_wallet_id=transfer.to_wallet_id,
        from_wallet_name=from_wallet.name if from_wallet else None,
        to_wallet_name=to_wallet.name if to_wallet else None,
        from_amount=Decimal(transfer.from_amount),
        to_amount=Decimal(transfer.to_amount),
        rate=Decimal(transfer.rate),
        from_currency=transfer.from_currency,
        to_currency=transfer.to_currency,
        business_date=transfer.business_date,
        operator_name=transfer.operator_name,
        note=transfer.note,
        created_at=transfer.created_at.isoformat() if transfer.created_at else "",
        deleted_at=transfer.deleted_at.isoformat() if transfer.deleted_at else None,
        transactions=tx_refs,
    )


# -------- 端点 --------


@router.post("", response_model=WalletTransferOut, status_code=status.HTTP_201_CREATED)
def create_wallet_transfer(
    request: WalletTransferCreateRequest,
    db: Session = Depends(get_db),
) -> WalletTransferOut:
    """创建划转单. 事务: 校验 → debit from → credit to → 建 transfer → 绑 tx."""
    try:
        transfer = create_transfer(
            db,
            from_wallet_id=request.from_wallet_id,
            to_wallet_id=request.to_wallet_id,
            from_amount=request.from_amount,
            to_amount=request.to_amount,
            business_date=request.business_date,
            operator_name=request.operator_name,
            note=request.note,
        )
    except ValueError as exc:
        db.rollback()
        message = str(exc)
        # 找不到钱包用 404, 其他业务校验失败用 400
        if "不存在" in message:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message) from exc
    except Exception:
        db.rollback()
        raise

    db.commit()
    db.refresh(transfer)
    return _serialize_transfer(db, transfer, include_tx=True)


@router.get("", response_model=list[WalletTransferOut])
def list_wallet_transfers(
    from_wallet_id: Optional[int] = Query(None),
    to_wallet_id: Optional[int] = Query(None),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    operator_name: Optional[str] = Query(None),
    include_deleted: bool = Query(False, description="是否含已撤销的"),
    db: Session = Depends(get_db),
) -> list[WalletTransferOut]:
    transfers = list_transfers(
        db,
        from_wallet_id=from_wallet_id,
        to_wallet_id=to_wallet_id,
        from_date=from_date,
        to_date=to_date,
        operator_name=operator_name,
        include_deleted=include_deleted,
    )
    # 列表为了性能不带流水明细, 想看 2 条流水去详情接口
    return [_serialize_transfer(db, t, include_tx=False) for t in transfers]


@router.get("/{transfer_id}", response_model=WalletTransferOut)
def get_wallet_transfer(transfer_id: int, db: Session = Depends(get_db)) -> WalletTransferOut:
    transfer = get_transfer(db, transfer_id)
    if transfer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="划转单不存在")
    return _serialize_transfer(db, transfer, include_tx=True)


@router.delete("/{transfer_id}", response_model=WalletTransferOut)
def cancel_wallet_transfer(transfer_id: int, db: Session = Depends(get_db)) -> WalletTransferOut:
    """撤销划转: 反向冲销 + 软删. 撤销后 to_wallet 余额需要够扣回."""
    try:
        transfer = cancel_transfer(db, transfer_id)
    except ValueError as exc:
        db.rollback()
        message = str(exc)
        if "不存在" in message:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message) from exc
    except Exception:
        db.rollback()
        raise

    db.commit()
    db.refresh(transfer)
    return _serialize_transfer(db, transfer, include_tx=True)
