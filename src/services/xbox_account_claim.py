"""XBOX 账号领取 / 归还流转。

CEO 2026-05-11 业务规则:
1. 账号必须 ``is_available_for_claim=True`` 才能被领
2. 一个账号同一时刻只能有 1 个有效领取（XboxAccountClaim.is_active=True）
3. 一个客服同一时刻最多 3 个有效领取
4. 下班手动归还,无自动兜底
5. CEO 可强制回收(用 force_recall=True 调归还,记 return_reason)
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select, func as sa_func
from sqlalchemy.orm import Session

from src.models.operator import Operator, XboxAccountClaim
from src.models.xbox import XboxAccount
from src.utils.time import china_now


MAX_CLAIMS_PER_OPERATOR = 3


class ClaimError(Exception):
    """领取/归还失败,业务约束违反。"""


def get_active_claim_for_account(
    session: Session, account_id: int
) -> Optional[XboxAccountClaim]:
    """该账号当前的有效领取(被谁领着)。"""
    return session.scalar(
        select(XboxAccountClaim).where(
            XboxAccountClaim.account_id == account_id,
            XboxAccountClaim.is_active.is_(True),
        )
    )


def list_active_claims_for_operator(
    session: Session, operator_id: int
) -> list[XboxAccountClaim]:
    """客服当前持有的所有账号领取。"""
    return list(
        session.scalars(
            select(XboxAccountClaim).where(
                XboxAccountClaim.operator_id == operator_id,
                XboxAccountClaim.is_active.is_(True),
            )
        )
    )


def count_active_claims_for_operator(session: Session, operator_id: int) -> int:
    return session.scalar(
        select(sa_func.count(XboxAccountClaim.id)).where(
            XboxAccountClaim.operator_id == operator_id,
            XboxAccountClaim.is_active.is_(True),
        )
    ) or 0


def claim_account(
    session: Session,
    *,
    account: XboxAccount,
    operator: Operator,
) -> XboxAccountClaim:
    """客服领取账号。

    校验:
    - account.is_available_for_claim 必须 True
    - account.status 必须 active
    - 该账号当前无其他人有效领取
    - operator 当前持有 < MAX_CLAIMS_PER_OPERATOR
    """
    if not account.is_available_for_claim:
        raise ClaimError(f"账号 {account.account_no or account.name} 未标记为'可出库'")
    if account.status != "active":
        raise ClaimError(
            f"账号当前状态为 {account.status},不可领取(只能领 active 的)"
        )
    if not operator.is_active:
        raise ClaimError("客服账号已停用")

    existing = get_active_claim_for_account(session, account.id)
    if existing is not None:
        raise ClaimError(
            f"账号已被 operator#{existing.operator_id} 领取,你不能再领"
        )

    current_count = count_active_claims_for_operator(session, operator.id)
    if current_count >= MAX_CLAIMS_PER_OPERATOR:
        raise ClaimError(
            f"你已持有 {current_count} 个账号,达到上限 {MAX_CLAIMS_PER_OPERATOR},请先归还后再领"
        )

    claim = XboxAccountClaim(
        account_id=account.id,
        operator_id=operator.id,
        is_active=True,
    )
    session.add(claim)
    session.flush()
    return claim


def return_claim(
    session: Session,
    *,
    claim: XboxAccountClaim,
    operator: Optional[Operator] = None,
    force_recall: bool = False,
) -> XboxAccountClaim:
    """归还账号。

    - 普通归还(客服在 exe 点'归还'): operator 是客服本人,return_reason="manual"
    - 强制回收(CEO 在财务系统点'强制回收'): force_recall=True,return_reason="force_recall_by_admin"

    若 claim 已经归还过(is_active=False) → 抛 ClaimError。
    若不是 force_recall 且 operator 不是 claim 持有人 → 抛 ClaimError。
    """
    if not claim.is_active:
        raise ClaimError("该领取已归还,不能重复归还")
    if not force_recall:
        if operator is None or operator.id != claim.operator_id:
            raise ClaimError("不能归还别人的领取,需要 force_recall")

    claim.returned_at = china_now()
    claim.is_active = False
    claim.return_reason = "force_recall_by_admin" if force_recall else "manual"
    session.flush()
    return claim


def list_available_accounts(session: Session) -> list[XboxAccount]:
    """可被领取的账号(is_available_for_claim=True + status=active + 无有效领取)。"""
    # 子查询: 当前被领取的账号 id
    claimed_subq = (
        select(XboxAccountClaim.account_id)
        .where(XboxAccountClaim.is_active.is_(True))
        .scalar_subquery()
    )
    return list(
        session.scalars(
            select(XboxAccount)
            .where(
                XboxAccount.is_available_for_claim.is_(True),
                XboxAccount.status == "active",
                XboxAccount.id.notin_(claimed_subq),
            )
            .order_by(XboxAccount.id)
        )
    )


def list_all_claims_with_active_filter(
    session: Session, only_active: bool = True
) -> list[XboxAccountClaim]:
    """CEO 后台用: 看所有领取记录。"""
    stmt = select(XboxAccountClaim).order_by(XboxAccountClaim.id.desc())
    if only_active:
        stmt = stmt.where(XboxAccountClaim.is_active.is_(True))
    return list(session.scalars(stmt))
