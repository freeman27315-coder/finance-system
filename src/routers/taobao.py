"""Taobao shop API routes."""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from src.database import get_db
from src.models.taobao import TaobaoShop
from src.models.wallet import Wallet
from src.services.taobao import list_taobao_shops


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


@router.get("/shops", response_model=list[TaobaoShopOut], response_model_by_alias=True)
def get_shops(db: Session = Depends(get_db)) -> list[TaobaoShopOut]:
    return [serialize_shop(shop) for shop in list_taobao_shops(db)]
