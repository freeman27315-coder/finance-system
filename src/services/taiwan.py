"""Taiwan wallet service functions."""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.wallet import Currency, Wallet, WalletType, create_wallet


# CEO 2026-05-17 改版: 台湾钱包结构改为 "3 个 group 父钱包 + 7 个子钱包"。
# 旧的 "8591余额 / 银行卡 / 超商代收金流余额" 已弃用并物理删除。
# 父钱包: 银行卡 / 8591 / 超商
# 子钱包: remark 字段存 "卡号: XXX  注册人: YYY"
_TAIWAN_GROUP_NAMES = ("银行卡", "8591", "超商")

_TAIWAN_CHILDREN: list[tuple[str, str, str | None]] = [
    # (group_name, wallet_name, remark)
    ("银行卡", "全支付",   "卡号: 389-11016050406250  注册人: 黄呈煜"),
    ("银行卡", "悠游付",   "卡号: 390-2202412224380826  注册人: 黄呈煜"),
    ("银行卡", "将来银行", "卡号: 823-88680933796132  注册人: 黄呈煜"),
    ("银行卡", "国泰银行", "卡号: 013-699520267321  注册人: 李睿旭"),
    ("8591",  "袋鼠8591", "注册人: 黄呈煜"),
    ("8591",  "喵喵8591", "注册人: 李睿旭"),
    ("超商",  "蓝新超商", None),
]


def ensure_default_taiwan_wallets(session: Session) -> None:
    """确保 3 个 group 父钱包 + 7 个子钱包都存在(创建缺失的, 不动已有的)。

    幂等: 重启后端不会重复建; 子钱包按 (parent, name) 唯一识别。
    """
    # 1. 建 3 个 group
    group_id_by_name: dict[str, int] = {}
    for name in _TAIWAN_GROUP_NAMES:
        existing = session.scalar(
            select(Wallet).where(
                Wallet.type == WalletType.TAIWAN.value,
                Wallet.currency == Currency.TWD.value,
                Wallet.name == name,
                Wallet.parent_id.is_(None),
                Wallet.deleted_at.is_(None),
            )
        )
        if existing is None:
            existing = create_wallet(
                session,
                name=name,
                wallet_type=WalletType.TAIWAN,
                currency=Currency.TWD,
                opening_balance=Decimal("0"),
                is_group=True,
            )
        group_id_by_name[name] = existing.id

    # 2. 建 7 个子钱包
    for group_name, child_name, remark in _TAIWAN_CHILDREN:
        parent_id = group_id_by_name[group_name]
        existing_child = session.scalar(
            select(Wallet).where(
                Wallet.type == WalletType.TAIWAN.value,
                Wallet.currency == Currency.TWD.value,
                Wallet.name == child_name,
                Wallet.parent_id == parent_id,
                Wallet.deleted_at.is_(None),
            )
        )
        if existing_child is None:
            create_wallet(
                session,
                name=child_name,
                wallet_type=WalletType.TAIWAN,
                currency=Currency.TWD,
                opening_balance=Decimal("0"),
                parent_id=parent_id,
                remark=remark,
            )
    session.flush()


def is_taiwan_wallet(wallet: Wallet) -> bool:
    wallet_type = wallet.type.value if isinstance(wallet.type, WalletType) else wallet.type
    currency = wallet.currency.value if isinstance(wallet.currency, Currency) else wallet.currency
    return wallet_type == WalletType.TAIWAN.value and currency == Currency.TWD.value


def list_taiwan_wallets(session: Session) -> list[Wallet]:
    # CEO 2026-05-17: 过滤软删除的钱包(老的 3 个 "8591余额/银行卡/超商代收金流余额" 已物理删,
    # 这里加个 deleted_at IS NULL 是防御性的, 避免以后又被软删错的钱包露出来)
    return list(
        session.scalars(
            select(Wallet)
            .where(
                Wallet.type == WalletType.TAIWAN.value,
                Wallet.currency == Currency.TWD.value,
                Wallet.deleted_at.is_(None),
            )
            .order_by(Wallet.parent_id.is_(None).desc(), Wallet.parent_id, Wallet.id)
        )
    )
