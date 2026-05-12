"""客服认证 + 账号领取相关 API。"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from src.database import get_db
from src.models.operator import Operator, XboxAccountClaim
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
from src.services.xbox_account_claim import (
    ClaimError,
    claim_account,
    count_active_claims_for_operator,
    list_active_claims_for_operator,
    list_all_claims_with_active_filter,
    list_available_accounts,
    return_claim,
)


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
