"""Taobao shop API routes."""
from __future__ import annotations

from decimal import Decimal
from io import BytesIO
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from src.database import get_db
from src.models.taobao import TaobaoShop
from src.models.wallet import Wallet
from src.services.taobao import list_taobao_shops
from src.services.taobao_import import (
    ImportReport,
    TaobaoImportError,
    import_qianniu_workbook,
)


router = APIRouter(prefix="/taobao", tags=["taobao"])


def _to_camel(snake: str) -> str:
    head, *tail = snake.split("_")
    return head + "".join(part.title() for part in tail)


class TaobaoShopWalletOut(BaseModel):
    id: int
    name: str
    balance: Decimal


class TaobaoShopOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=_to_camel)

    id: int
    name: str
    payment_wallet: Optional[TaobaoShopWalletOut] = Field(default=None)
    unconfirmed_alipay: TaobaoShopWalletOut
    unconfirmed_wechat: TaobaoShopWalletOut
    aggregator_frozen: TaobaoShopWalletOut
    aggregator_available: TaobaoShopWalletOut
    bank_card: TaobaoShopWalletOut
    remark: Optional[str] = None
    created_at: str


class TaobaoImportReportOut(BaseModel):
    """ImportReport 的 camelCase 输出。"""

    model_config = ConfigDict(populate_by_name=True, alias_generator=_to_camel)

    shop_name: str
    total_rows_parsed: int
    created_orders: int
    status_changed_orders: int
    closed_reverted: int
    skipped_no_change: int
    skipped_unpaid_or_unshipped: int
    skipped_unknown_payment: int
    errors: list[str] = Field(default_factory=list)


def _serialize_wallet(wallet: Wallet) -> TaobaoShopWalletOut:
    return TaobaoShopWalletOut(
        id=wallet.id,
        name=wallet.name,
        balance=wallet.balance,
    )


def serialize_shop(shop: TaobaoShop) -> TaobaoShopOut:
    return TaobaoShopOut(
        id=shop.id,
        name=shop.name,
        payment_wallet=(
            _serialize_wallet(shop.payment_wallet)
            if shop.payment_wallet is not None
            else None
        ),
        unconfirmed_alipay=_serialize_wallet(shop.unconfirmed_alipay_wallet),
        unconfirmed_wechat=_serialize_wallet(shop.unconfirmed_wechat_wallet),
        aggregator_frozen=_serialize_wallet(shop.aggregator_frozen_wallet),
        aggregator_available=_serialize_wallet(shop.aggregator_available_wallet),
        bank_card=_serialize_wallet(shop.bank_card_wallet),
        remark=shop.remark,
        created_at=shop.created_at.isoformat() if shop.created_at else "",
    )


def _serialize_report(report: ImportReport) -> TaobaoImportReportOut:
    return TaobaoImportReportOut(
        shop_name=report.shop_name,
        total_rows_parsed=report.total_rows_parsed,
        created_orders=report.created_orders,
        status_changed_orders=report.status_changed_orders,
        closed_reverted=report.closed_reverted,
        skipped_no_change=report.skipped_no_change,
        skipped_unpaid_or_unshipped=report.skipped_unpaid_or_unshipped,
        skipped_unknown_payment=report.skipped_unknown_payment,
        errors=list(report.errors),
    )


@router.get("/shops", response_model=list[TaobaoShopOut], response_model_by_alias=True)
def get_shops(db: Session = Depends(get_db)) -> list[TaobaoShopOut]:
    return [serialize_shop(shop) for shop in list_taobao_shops(db)]


@router.post(
    "/shops/{shop_id}/import",
    response_model=TaobaoImportReportOut,
    response_model_by_alias=True,
    status_code=status.HTTP_200_OK,
)
def import_qianniu_excel(
    shop_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> TaobaoImportReportOut:
    """上传千牛后台导出的 .xlsx，按规则入账每条订单并对老订单做 reconcile。

    - 404：店铺不存在
    - 400：文件不是 .xlsx 或表头/列结构不符
    - 整个导入是单一事务：任何一行抛异常都 rollback，不会半成功
    """
    # 1. 店铺存在性校验
    shop = db.get(TaobaoShop, shop_id)
    if shop is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="店铺不存在")

    # 2. 文件类型校验（按后缀；content-type 在不同客户端表现不一）
    filename = (file.filename or "").lower()
    if not filename.endswith(".xlsx"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="仅支持 .xlsx 文件",
        )

    # 3. 读取 + 解析 + 入账（原子事务）
    raw_bytes = file.file.read()
    if not raw_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="文件为空",
        )

    try:
        report = import_qianniu_workbook(db, shop, BytesIO(raw_bytes))
        db.commit()
    except TaobaoImportError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise

    return _serialize_report(report)
