"""客服认证 + 账号领取相关 API。"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.database import get_db
from src.models.operator import Operator, XboxAccountClaim
from src.models.xbox import XboxAccount, XboxOrder, XboxOrderStatus
from src.services.operator_auth import (
    AuthError,
    confirm_totp,
    create_operator,
    deactivate_operator,
    get_operator,
    list_operators,
    login as service_login,
    reactivate_operator,
    totp_qrcode_png_base64,
    totp_provisioning_uri,
)
from src.services.xbox_account import reveal_password
from src.services.xbox_account_claim import (
    ClaimError,
    claim_account,
    count_active_claims_for_operator,
    get_active_claim_for_account,
    list_active_claims_for_operator,
    list_all_claims_with_active_filter,
    list_available_accounts,
    return_claim,
)
from src.services.xbox_order import update_order_completion
from src.services.xbox_sync import trigger_sync
from src.utils.crypto import CryptoError


router = APIRouter(prefix="/operator", tags=["operator"])


def _to_camel(snake: str) -> str:
    head, *tail = snake.split("_")
    return head + "".join(part.title() for part in tail)


# ---------- Schemas ----------


class OperatorCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=_to_camel)

    login_name: str = Field(..., min_length=1, max_length=64)
    display_name: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=6)
    remark: Optional[str] = None


class OperatorOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=_to_camel)

    id: int
    login_name: str
    display_name: str
    totp_confirmed: bool
    is_active: bool
    remark: Optional[str] = None
    created_at: str
    last_login_at: Optional[str] = None


class OperatorTotpSetupOut(BaseModel):
    """创建客服后返回 TOTP 绑定信息(qr + secret + URI)。"""

    model_config = ConfigDict(populate_by_name=True, alias_generator=_to_camel)

    operator_id: int
    totp_secret: str  # base32, 客服可手动输入到 App
    totp_uri: str  # otpauth:// URI
    totp_qr_png_base64: str  # 二维码图片 base64,前端 <img src="data:image/png;base64,..."> 显示


class OperatorTotpConfirm(BaseModel):
    code: str = Field(..., min_length=6, max_length=6)


class OperatorLoginRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=_to_camel)

    login_name: str
    password: str
    totp_code: str = Field(..., min_length=6, max_length=6)


class OperatorLoginOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=_to_camel)

    token: str
    operator: dict


class XboxAccountClaimOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=_to_camel)

    id: int
    account_id: int
    operator_id: int
    claimed_at: str
    returned_at: Optional[str] = None
    is_active: bool
    return_reason: Optional[str] = None


class ClaimRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=_to_camel)

    account_id: int
    operator_id: int  # 暂用,后续 exe 用 JWT token 自动带


class ReturnRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=_to_camel)

    operator_id: Optional[int] = None  # 普通归还填本人
    force_recall: bool = False  # CEO 强制回收


def _serialize_operator(op: Operator) -> OperatorOut:
    return OperatorOut(
        id=op.id,
        login_name=op.login_name,
        display_name=op.display_name,
        totp_confirmed=op.totp_confirmed,
        is_active=op.is_active,
        remark=op.remark,
        created_at=op.created_at.isoformat() if op.created_at else "",
        last_login_at=op.last_login_at.isoformat() if op.last_login_at else None,
    )


def _serialize_claim(claim: XboxAccountClaim) -> XboxAccountClaimOut:
    return XboxAccountClaimOut(
        id=claim.id,
        account_id=claim.account_id,
        operator_id=claim.operator_id,
        claimed_at=claim.claimed_at.isoformat() if claim.claimed_at else "",
        returned_at=claim.returned_at.isoformat() if claim.returned_at else None,
        is_active=claim.is_active,
        return_reason=claim.return_reason,
    )


# ---------- 客服管理 (CEO 后台用) ----------


@router.post(
    "/operators",
    response_model=OperatorTotpSetupOut,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
)
def create_operator_endpoint(
    request: OperatorCreate,
    db: Session = Depends(get_db),
) -> OperatorTotpSetupOut:
    """CEO 创建客服。返回 TOTP 绑定二维码,客服拿去扫码。"""
    try:
        op = create_operator(
            db,
            login_name=request.login_name,
            display_name=request.display_name,
            password=request.password,
            remark=request.remark,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    db.refresh(op)
    return OperatorTotpSetupOut(
        operator_id=op.id,
        totp_secret=op.totp_secret,
        totp_uri=totp_provisioning_uri(op.totp_secret, op.login_name),
        totp_qr_png_base64=totp_qrcode_png_base64(op.totp_secret, op.login_name),
    )


@router.get(
    "/operators",
    response_model=list[OperatorOut],
    response_model_by_alias=True,
)
def list_operators_endpoint(db: Session = Depends(get_db)) -> list[OperatorOut]:
    return [_serialize_operator(op) for op in list_operators(db)]


@router.get(
    "/operators/{operator_id}/totp-qr",
    response_model=OperatorTotpSetupOut,
    response_model_by_alias=True,
)
def get_totp_qr_endpoint(
    operator_id: int,
    db: Session = Depends(get_db),
) -> OperatorTotpSetupOut:
    """重看 TOTP 二维码(客服扔了二维码可重新看)。"""
    op = get_operator(db, operator_id)
    if op is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="客服不存在")
    return OperatorTotpSetupOut(
        operator_id=op.id,
        totp_secret=op.totp_secret,
        totp_uri=totp_provisioning_uri(op.totp_secret, op.login_name),
        totp_qr_png_base64=totp_qrcode_png_base64(op.totp_secret, op.login_name),
    )


@router.post(
    "/operators/{operator_id}/confirm-totp",
    response_model=OperatorOut,
    response_model_by_alias=True,
)
def confirm_totp_endpoint(
    operator_id: int,
    request: OperatorTotpConfirm,
    db: Session = Depends(get_db),
) -> OperatorOut:
    """客服扫码后输入 6 位验证码确认绑定。"""
    op = get_operator(db, operator_id)
    if op is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="客服不存在")
    if not confirm_totp(db, op, request.code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="验证码错误,请检查 App 时间是否同步",
        )
    db.commit()
    db.refresh(op)
    return _serialize_operator(op)


@router.patch(
    "/operators/{operator_id}/deactivate",
    response_model=OperatorOut,
    response_model_by_alias=True,
)
def deactivate_endpoint(operator_id: int, db: Session = Depends(get_db)) -> OperatorOut:
    op = get_operator(db, operator_id)
    if op is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="客服不存在")
    deactivate_operator(db, op)
    db.commit()
    db.refresh(op)
    return _serialize_operator(op)


@router.patch(
    "/operators/{operator_id}/reactivate",
    response_model=OperatorOut,
    response_model_by_alias=True,
)
def reactivate_endpoint(operator_id: int, db: Session = Depends(get_db)) -> OperatorOut:
    op = get_operator(db, operator_id)
    if op is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="客服不存在")
    reactivate_operator(db, op)
    db.commit()
    db.refresh(op)
    return _serialize_operator(op)


# ---------- 客服登录 ----------


@router.post(
    "/login",
    response_model=OperatorLoginOut,
    response_model_by_alias=True,
)
def login_endpoint(
    request: OperatorLoginRequest,
    db: Session = Depends(get_db),
) -> OperatorLoginOut:
    """三要素登录: login_name + password + TOTP 6 位。"""
    try:
        result = service_login(
            db,
            login_name=request.login_name,
            password=request.password,
            totp_code=request.totp_code,
        )
    except AuthError as exc:
        # 不暴露具体原因(账号不存在/密码错/TOTP 错统一拒绝)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
    db.commit()
    return OperatorLoginOut(**result)


# ---------- 账号领取 / 归还 ----------


@router.get(
    "/available-accounts",
    response_model=list[dict],
)
def list_available_endpoint(db: Session = Depends(get_db)) -> list[dict]:
    """当前可领取的账号(is_available_for_claim + status=active + 未被领)。"""
    accounts = list_available_accounts(db)
    return [
        {
            "id": a.id,
            "accountNo": a.account_no,
            "name": a.name,
            "country": a.country.value if hasattr(a.country, "value") else a.country,
            "loginEmail": a.login_email,
            "exchangeRate": str(a.exchange_rate) if a.exchange_rate else None,
        }
        for a in accounts
    ]


@router.post(
    "/claims",
    response_model=XboxAccountClaimOut,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
)
def claim_account_endpoint(
    request: ClaimRequest,
    db: Session = Depends(get_db),
) -> XboxAccountClaimOut:
    """客服领取账号。"""
    from src.models.xbox import XboxAccount

    account = db.get(XboxAccount, request.account_id)
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账号不存在")
    operator = get_operator(db, request.operator_id)
    if operator is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="客服不存在")
    try:
        claim = claim_account(db, account=account, operator=operator)
    except ClaimError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    db.refresh(claim)
    return _serialize_claim(claim)


@router.post(
    "/claims/{claim_id}/return",
    response_model=XboxAccountClaimOut,
    response_model_by_alias=True,
)
def return_claim_endpoint(
    claim_id: int,
    request: ReturnRequest,
    db: Session = Depends(get_db),
) -> XboxAccountClaimOut:
    claim = db.get(XboxAccountClaim, claim_id)
    if claim is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="领取记录不存在")
    operator = None
    if request.operator_id is not None:
        operator = get_operator(db, request.operator_id)
    try:
        return_claim(
            db,
            claim=claim,
            operator=operator,
            force_recall=request.force_recall,
        )
    except ClaimError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    db.refresh(claim)
    return _serialize_claim(claim)


@router.get(
    "/operators/{operator_id}/claims",
    response_model=list[XboxAccountClaimOut],
    response_model_by_alias=True,
)
def list_my_claims_endpoint(
    operator_id: int,
    db: Session = Depends(get_db),
) -> list[XboxAccountClaimOut]:
    """客服当前持有的领取(查我的账号)。"""
    return [_serialize_claim(c) for c in list_active_claims_for_operator(db, operator_id)]


@router.get(
    "/claims",
    response_model=list[XboxAccountClaimOut],
    response_model_by_alias=True,
)
def list_all_claims_endpoint(
    only_active: bool = True,
    db: Session = Depends(get_db),
) -> list[XboxAccountClaimOut]:
    """CEO 后台: 看所有领取记录(默认仅活跃,可看历史)。"""
    return [_serialize_claim(c) for c in list_all_claims_with_active_filter(db, only_active)]


# ===================================================================
# 客服 exe: 账号详情 + 同步 + 补销售信息 (CEO 2026-05-12 PR-C)
# ===================================================================


def _require_holding(
    db: Session, account_id: int, operator_id: int
) -> tuple[XboxAccount, Operator]:
    """校验 operator 当前持有此账号(active claim)。返回 (account, operator)。

    任意一个不满足都抛 403/404。
    """
    account = db.get(XboxAccount, account_id)
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账号不存在")
    operator = get_operator(db, operator_id)
    if operator is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="客服不存在")
    if not operator.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="客服账号已停用")

    claim = get_active_claim_for_account(db, account_id)
    if claim is None or claim.operator_id != operator_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="你没有领取这个账号,无权操作",
        )
    return account, operator


class OperatorAccountDetailOut(BaseModel):
    """客服看的账号详情(含密码明文 + 当前余额)。"""

    model_config = ConfigDict(populate_by_name=True, alias_generator=_to_camel)

    id: int
    account_no: Optional[str]
    name: str
    country: str
    currency: str
    login_email: Optional[str]
    password_plain: Optional[str]  # 解密后明文(客服需要拿来登录 Microsoft)
    exchange_rate: Optional[str]
    local_balance: str  # 微软账号当前本币余额(同步后会更新)
    status: str
    status_message: Optional[str]
    last_synced_at: Optional[str]


@router.get(
    "/accounts/{account_id}",
    response_model=OperatorAccountDetailOut,
    response_model_by_alias=True,
)
def get_account_detail_endpoint(
    account_id: int,
    operator_id: int = Query(..., alias="operatorId"),
    db: Session = Depends(get_db),
) -> OperatorAccountDetailOut:
    """客服 exe 看账号详情(密码明文 + 当前余额)。

    校验: 必须是当前持有此账号的客服。
    """
    account, _ = _require_holding(db, account_id, operator_id)

    password_plain: Optional[str] = None
    if account.password_enc:
        try:
            password_plain = reveal_password(account)
        except (CryptoError, ValueError):
            password_plain = None  # 密钥配置错或密文损坏,不阻塞详情展示

    return OperatorAccountDetailOut(
        id=account.id,
        account_no=account.account_no,
        name=account.name,
        country=account.country.value if hasattr(account.country, "value") else account.country,
        currency=account.currency.value if hasattr(account.currency, "value") else account.currency,
        login_email=account.login_email,
        password_plain=password_plain,
        exchange_rate=str(account.exchange_rate) if account.exchange_rate is not None else None,
        local_balance=str(account.local_balance or Decimal("0")),
        status=account.status,
        status_message=account.status_message,
        last_synced_at=account.last_synced_at.isoformat() if account.last_synced_at else None,
    )


class OperatorSyncRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=_to_camel)

    operator_id: int
    count: int = 20  # 10 / 20 / 30 / 50


@router.post(
    "/accounts/{account_id}/sync-orders",
    response_model=dict,
)
def operator_sync_orders_endpoint(
    account_id: int,
    request: OperatorSyncRequest,
    db: Session = Depends(get_db),
) -> dict:
    """客服触发该账号的 Microsoft 订单同步。

    校验: 必须是当前持有此账号的客服。
    返回: {batchId, success, ordersAdded, ordersSkipped, balance, failure}
    """
    account, _ = _require_holding(db, account_id, request.operator_id)
    try:
        result = trigger_sync(db, account, count=request.count)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    db.commit()
    return result


class OperatorOrderOut(BaseModel):
    """客服 exe 看的订单(简化版,只暴露客服需要的字段)。

    CEO 2026-05-12: 历史订单表展示 9 列 — 字段都映射到这里。
    """

    model_config = ConfigDict(populate_by_name=True, alias_generator=_to_camel)

    id: int
    account_id: int
    account_no: Optional[str]  # 账号编号(给历史订单表用,免去前端再查)
    order_no: str
    amount_local: str
    currency_local: str
    order_at: str
    sale_date: Optional[str]
    status: str
    product_name: Optional[str]
    operator_name: Optional[str]  # 经办人(=补销售时填的客服名)
    sale_price: Optional[str]
    sale_currency: Optional[str]
    wallet_method_id: Optional[int]
    wallet_method_label: Optional[str]  # 收款方式 label(展示用)
    wallet_item_id: Optional[int]
    wallet_item_label: Optional[str]  # 备注模板 label(展示用)
    remark: Optional[str]  # CEO 2026-05-12: 客服自由填写的备注


def _serialize_op_order(
    order: XboxOrder,
    *,
    account_no_map: Optional[dict[int, Optional[str]]] = None,
    method_label_map: Optional[dict[int, str]] = None,
    item_label_map: Optional[dict[int, str]] = None,
) -> OperatorOrderOut:
    """序列化客服 exe 端订单。可传 label 映射避免每行单独 query。"""
    return OperatorOrderOut(
        id=order.id,
        account_id=order.account_id,
        account_no=(account_no_map or {}).get(order.account_id),
        order_no=order.order_no,
        amount_local=str(order.amount_local),
        currency_local=order.currency_local,
        order_at=order.order_at.isoformat() if order.order_at else "",
        sale_date=order.sale_date.isoformat() if order.sale_date else None,
        status=order.status,
        product_name=order.product_name,
        operator_name=order.operator_name,
        sale_price=str(order.sale_price) if order.sale_price is not None else None,
        sale_currency=order.sale_currency,
        wallet_method_id=order.wallet_method_id,
        wallet_method_label=(
            (method_label_map or {}).get(order.wallet_method_id)
            if order.wallet_method_id is not None
            else None
        ),
        wallet_item_id=order.wallet_item_id,
        wallet_item_label=(
            (item_label_map or {}).get(order.wallet_item_id)
            if order.wallet_item_id is not None
            else None
        ),
        remark=order.remark,
    )


@router.get(
    "/accounts/{account_id}/orders",
    response_model=list[OperatorOrderOut],
    response_model_by_alias=True,
)
def operator_list_orders_endpoint(
    account_id: int,
    operator_id: int = Query(..., alias="operatorId"),
    only_pending: bool = Query(False, alias="onlyPending"),
    db: Session = Depends(get_db),
) -> list[OperatorOrderOut]:
    """客服看该账号的订单列表。

    CEO 2026-05-12: 默认返回**所有历史订单**(pending + converted),展示在工作台
    主表里;只看待补可传 onlyPending=true。
    """
    account, _ = _require_holding(db, account_id, operator_id)
    stmt = select(XboxOrder).where(XboxOrder.account_id == account_id)
    if only_pending:
        stmt = stmt.where(XboxOrder.status == XboxOrderStatus.PENDING_COMPLETE.value)
    stmt = stmt.order_by(XboxOrder.order_at.desc())
    orders = list(db.scalars(stmt))

    # 一次性查 method/item labels(避免每行 query)
    from src.models.xbox import XboxWalletItem, XboxWalletMethod

    method_ids = {o.wallet_method_id for o in orders if o.wallet_method_id is not None}
    item_ids = {o.wallet_item_id for o in orders if o.wallet_item_id is not None}
    method_label_map: dict[int, str] = {}
    item_label_map: dict[int, str] = {}
    if method_ids:
        for m in db.scalars(select(XboxWalletMethod).where(XboxWalletMethod.id.in_(method_ids))):
            method_label_map[m.id] = m.label
    if item_ids:
        for it in db.scalars(select(XboxWalletItem).where(XboxWalletItem.id.in_(item_ids))):
            item_label_map[it.id] = it.label

    account_no_map = {account.id: account.account_no}
    return [
        _serialize_op_order(
            o,
            account_no_map=account_no_map,
            method_label_map=method_label_map,
            item_label_map=item_label_map,
        )
        for o in orders
    ]


class OperatorOrderCompletion(BaseModel):
    """客服补销售信息。销售日期 + 经办人系统自动填,
    客服填: 商品 / 售价 / 币种 / 收款方式 / 备注模板 / 备注(可自由填写)。
    """

    model_config = ConfigDict(populate_by_name=True, alias_generator=_to_camel)

    operator_id: int
    product_name: str = Field(..., min_length=1, max_length=255)
    sale_price: Decimal
    sale_currency: str
    wallet_method_id: int
    wallet_item_id: int
    remark: Optional[str] = None  # CEO 2026-05-12: 客服自由填写


@router.patch(
    "/orders/{order_id}/completion",
    response_model=OperatorOrderOut,
    response_model_by_alias=True,
)
def operator_complete_order_endpoint(
    order_id: int,
    request: OperatorOrderCompletion,
    db: Session = Depends(get_db),
) -> OperatorOrderOut:
    """客服补销售信息(自动经办人 = 客服显示名;销售日期已自动 = order_at)。

    校验: 客服必须持有该订单对应的账号。
    成功后订单 status 变 converted(若所有字段就位)。
    """
    order = db.get(XboxOrder, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="订单不存在")
    account, operator = _require_holding(db, order.account_id, request.operator_id)

    try:
        update_order_completion(
            db,
            order,
            # sale_date 不传 → 保持自动填的 order_at
            product_name=request.product_name.strip(),
            # 经办人系统自动填(CEO 2026-05-11: 自动填客服名字)
            operator_name=operator.display_name,
            sale_price=request.sale_price,
            sale_currency=request.sale_currency,
            wallet_method_id=request.wallet_method_id,
            wallet_item_id=request.wallet_item_id,
        )
        # CEO 2026-05-12: 备注独立字段, 不走 update_order_completion (它不管 remark)
        if request.remark is not None:
            order.remark = request.remark.strip() or None
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    db.commit()
    db.refresh(order)

    # 序列化时填 labels 给前端
    from src.models.xbox import XboxWalletItem, XboxWalletMethod

    method_label_map = {}
    item_label_map = {}
    if order.wallet_method_id is not None:
        m = db.get(XboxWalletMethod, order.wallet_method_id)
        if m:
            method_label_map[m.id] = m.label
    if order.wallet_item_id is not None:
        it = db.get(XboxWalletItem, order.wallet_item_id)
        if it:
            item_label_map[it.id] = it.label
    return _serialize_op_order(
        order,
        account_no_map={account.id: account.account_no},
        method_label_map=method_label_map,
        item_label_map=item_label_map,
    )
