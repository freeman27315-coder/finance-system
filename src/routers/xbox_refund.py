"""XBOX 退款单 HTTP 路由(Issue #130 / CEO 2026-05-18)。

端点:
- POST   /api/xbox/refunds          创建退款单
- GET    /api/xbox/refunds          列表 + 筛选
- GET    /api/xbox/refunds/{id}     详情
- DELETE /api/xbox/refunds/{id}     撤销退款(硬删 + 反向冲销)

退款单 = 全额退一笔 XBOX 销售记录, 一笔退款触发:
- 实际钱包 OUT(走标准 debit, 有余额校验)
- 理论钱包 OUT(跳过余额校验, XBOX_SALES_LEDGER 允许负余额)
- 销售记录标 refunded
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.database import get_db
from src.models.wallet import Wallet
from src.models.xbox import XboxRefund, XboxSaleRecord
from src.services.xbox_refund import (
    cancel_refund,
    create_refund,
    get_refund,
    list_refunds,
)


router = APIRouter()


# -------- Pydantic 模型 --------


class XboxRefundCreateRequest(BaseModel):
    sale_record_id: int = Field(..., gt=0)
    actual_wallet_id: int = Field(..., gt=0, description="实际从哪个钱包扣钱")
    business_date: Optional[date] = None
    operator_name: Optional[str] = Field(None, max_length=120)
    note: Optional[str] = None


class XboxRefundSaleRecordSummary(BaseModel):
    """退款单关联的原销售记录摘要(列表/详情都用)."""

    id: int
    account_id: int
    product_name: str
    operator_name: str
    sale_price: Decimal
    sale_currency: str
    wallet_pool_id: int


class XboxRefundOut(BaseModel):
    id: int
    original_sale_record_id: int
    refund_amount: Decimal
    refund_currency: str
    actual_wallet_id: int
    actual_wallet_name: Optional[str] = None
    theoretical_wallet_id: int
    theoretical_wallet_name: Optional[str] = None
    business_date: Optional[date] = None
    operator_name: Optional[str] = None
    note: Optional[str] = None
    actual_bookkeeping_tx_id: Optional[int] = None
    theoretical_bookkeeping_tx_id: Optional[int] = None
    created_at: str
    sale_record: Optional[XboxRefundSaleRecordSummary] = None


def _serialize_refund(session: Session, refund: XboxRefund) -> XboxRefundOut:
    actual_wallet = session.get(Wallet, refund.actual_wallet_id)
    theoretical_wallet = session.get(Wallet, refund.theoretical_wallet_id)

    sale_record_summary: Optional[XboxRefundSaleRecordSummary] = None
    record = session.get(XboxSaleRecord, refund.original_sale_record_id)
    if record is not None:
        sale_record_summary = XboxRefundSaleRecordSummary(
            id=record.id,
            account_id=record.account_id,
            product_name=record.product_name,
            operator_name=record.operator_name,
            sale_price=Decimal(record.sale_price),
            sale_currency=record.sale_currency,
            wallet_pool_id=record.wallet_pool_id,
        )

    return XboxRefundOut(
        id=refund.id,
        original_sale_record_id=refund.original_sale_record_id,
        refund_amount=Decimal(refund.refund_amount),
        refund_currency=refund.refund_currency,
        actual_wallet_id=refund.actual_wallet_id,
        actual_wallet_name=actual_wallet.name if actual_wallet else None,
        theoretical_wallet_id=refund.theoretical_wallet_id,
        theoretical_wallet_name=theoretical_wallet.name if theoretical_wallet else None,
        business_date=refund.business_date,
        operator_name=refund.operator_name,
        note=refund.note,
        actual_bookkeeping_tx_id=refund.actual_bookkeeping_tx_id,
        theoretical_bookkeeping_tx_id=refund.theoretical_bookkeeping_tx_id,
        created_at=refund.created_at.isoformat() if refund.created_at else "",
        sale_record=sale_record_summary,
    )


# -------- 端点 --------


@router.post("", response_model=XboxRefundOut, status_code=status.HTTP_201_CREATED)
def create_xbox_refund(
    request: XboxRefundCreateRequest,
    db: Session = Depends(get_db),
) -> XboxRefundOut:
    """创建退款单. 事务: 校验 → debit 实际 → force_debit 理论 → 建 refund → 销售记录改 refunded."""
    try:
        refund = create_refund(
            db,
            sale_record_id=request.sale_record_id,
            actual_wallet_id=request.actual_wallet_id,
            business_date=request.business_date,
            operator_name=request.operator_name,
            note=request.note,
        )
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
    db.refresh(refund)
    return _serialize_refund(db, refund)


@router.get("", response_model=list[XboxRefundOut])
def list_xbox_refunds(
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    actual_wallet_id: Optional[int] = Query(None),
    operator_name: Optional[str] = Query(None),
    db: Session = Depends(get_db),
) -> list[XboxRefundOut]:
    refunds = list_refunds(
        db,
        from_date=from_date,
        to_date=to_date,
        actual_wallet_id=actual_wallet_id,
        operator_name=operator_name,
    )
    return [_serialize_refund(db, r) for r in refunds]


@router.get("/{refund_id}", response_model=XboxRefundOut)
def get_xbox_refund(refund_id: int, db: Session = Depends(get_db)) -> XboxRefundOut:
    refund = get_refund(db, refund_id)
    if refund is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="退款单不存在")
    return _serialize_refund(db, refund)


@router.delete("/{refund_id}", status_code=status.HTTP_200_OK)
def cancel_xbox_refund(refund_id: int, db: Session = Depends(get_db)) -> dict:
    """撤销退款: 反向冲销 + 硬删. 因为 original_sale_record_id UNIQUE, 软删
    会让"同一销售记录再次退款"违反约束, 所以硬删.
    """
    try:
        refund = cancel_refund(db, refund_id)
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
    return {
        "ok": True,
        "cancelled_refund_id": refund.id,
        "original_sale_record_id": refund.original_sale_record_id,
    }
