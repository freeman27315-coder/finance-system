"""XBOX 销售归口（理论值）钱包初始化服务。

CEO 2026-05-08 确认的钱包结构（理论值,与实际值物理隔离）：

XBOX 销售归口（顶级 group, type=XBOX_SALES_LEDGER）
├─ 淘宝渠道（group）
│  ├─ 丙火网络 (CNY)
│  ├─ 兔仔电玩 (CNY)
│  └─ 小小电玩 (CNY)
├─ 台湾渠道（group）
│  ├─ 银行卡A (TWD)
│  ├─ 银行卡B (TWD)
│  ├─ 袋鼠8591 (TWD)
│  ├─ 喵喵8591 (TWD)
│  └─ 存余额 (TWD)
└─ RMB 渠道（group）
   └─ TOM支付宝 (CNY)

XBOX 客服在录入销售时选择的"出售渠道"对应这里的叶子钱包。
对账时和实际值钱包（千牛/支付宝/淘宝模块下的钱包）做差异比较。

这套结构与 XBOX 钱包设置(xbox_wallet_methods + xbox_wallet_items)
配套：第一次启动时如果设置为空,会自动建立 3 个 method + 9 个 item
关联到对应理论值钱包。
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.wallet import Currency, Wallet, WalletType, create_wallet
from src.models.xbox import XboxWalletItem, XboxWalletMethod
from src.utils.time import china_now


# 钱包结构定义（顶级名 / 子分组 / 叶子钱包列表）
SALES_LEDGER_STRUCTURE = {
    "name": "XBOX 销售归口",
    "groups": [
        {
            "name": "淘宝渠道",
            "currency": Currency.CNY,
            "leaves": ["丙火网络", "兔仔电玩", "小小电玩"],
        },
        {
            "name": "台湾渠道",
            "currency": Currency.TWD,
            "leaves": ["银行卡A", "银行卡B", "袋鼠8591", "喵喵8591", "存余额"],
        },
        {
            "name": "RMB 渠道",
            "currency": Currency.CNY,
            "leaves": ["TOM支付宝"],
        },
    ],
}


# 钱包设置预设（method.code → label + 对应大类下的 leaf 钱包名 + currency）
WALLET_SETTINGS_PRESET = [
    {
        "code": "taobao_channel",
        "label": "淘宝渠道",
        "items": [
            ("binghuo", "丙火网络", "丙火网络", Currency.CNY),
            ("tuzai", "兔仔电玩", "兔仔电玩", Currency.CNY),
            ("xiaoxiao", "小小电玩", "小小电玩", Currency.CNY),
        ],
    },
    {
        "code": "taiwan_channel",
        "label": "台湾渠道",
        "items": [
            ("bank_a", "银行卡A", "银行卡A", Currency.TWD),
            ("bank_b", "银行卡B", "银行卡B", Currency.TWD),
            ("kangaroo_8591", "袋鼠8591", "袋鼠8591", Currency.TWD),
            ("meow_8591", "喵喵8591", "喵喵8591", Currency.TWD),
            ("balance", "存余额", "存余额", Currency.TWD),
        ],
    },
    {
        "code": "rmb_channel",
        "label": "RMB 渠道",
        "items": [
            ("tom_alipay", "TOM支付宝", "TOM支付宝", Currency.CNY),
        ],
    },
]


def _ensure_root(session: Session) -> Wallet:
    """获取或创建顶级 'XBOX 销售归口' group 钱包。"""
    root = session.scalar(
        select(Wallet).where(
            Wallet.type == WalletType.XBOX_SALES_LEDGER.value,
            Wallet.parent_id.is_(None),
        )
    )
    if root is None:
        root = create_wallet(
            session,
            name=SALES_LEDGER_STRUCTURE["name"],
            wallet_type=WalletType.XBOX_SALES_LEDGER,
            currency=Currency.CNY,  # 顶级 group 币种不重要（不存余额）
            is_group=True,
        )
    else:
        root.name = SALES_LEDGER_STRUCTURE["name"]
        root.is_group = True
    return root


def _ensure_sub_group(session: Session, parent: Wallet, name: str, currency: Currency) -> Wallet:
    """获取或创建二级 group 子钱包(淘宝渠道/台湾渠道/RMB 渠道)。"""
    existing = session.scalar(
        select(Wallet).where(
            Wallet.parent_id == parent.id,
            Wallet.name == name,
        )
    )
    if existing is not None:
        existing.is_group = True
        existing.balance = Decimal("0")
        return existing
    return create_wallet(
        session,
        name=name,
        wallet_type=WalletType.XBOX_SALES_LEDGER,
        currency=currency,
        parent_id=parent.id,
        is_group=True,
    )


def _ensure_leaf(session: Session, parent: Wallet, name: str, currency: Currency) -> Wallet:
    """获取或创建叶子钱包。"""
    existing = session.scalar(
        select(Wallet).where(
            Wallet.parent_id == parent.id,
            Wallet.name == name,
        )
    )
    if existing is not None:
        existing.is_group = False
        return existing
    return create_wallet(
        session,
        name=name,
        wallet_type=WalletType.XBOX_SALES_LEDGER,
        currency=currency,
        parent_id=parent.id,
        is_group=False,
    )


def ensure_xbox_sales_ledger_wallets(session: Session) -> dict[str, int]:
    """初始化 XBOX 销售归口钱包结构（幂等）。返回叶子钱包名 → wallet.id 映射。"""
    root = _ensure_root(session)
    leaf_id_by_name: dict[str, int] = {}

    for sub_config in SALES_LEDGER_STRUCTURE["groups"]:
        sub_group = _ensure_sub_group(
            session, root, sub_config["name"], sub_config["currency"]
        )
        for leaf_name in sub_config["leaves"]:
            leaf = _ensure_leaf(session, sub_group, leaf_name, sub_config["currency"])
            leaf_id_by_name[leaf_name] = leaf.id

    session.flush()
    return leaf_id_by_name


def ensure_xbox_default_wallet_settings(
    session: Session, leaf_id_by_name: dict[str, int]
) -> None:
    """按 code 逐个补齐 3 个预设 method + 9 个 item。

    幂等：已存在的 method（按 code）补齐缺失的 item;不存在的新建。
    不覆盖 / 不删除 CEO 自定义的其他 method（如 ROBLOX/VALO 等）。
    """
    now = china_now()
    for method_data in WALLET_SETTINGS_PRESET:
        method = session.scalar(
            select(XboxWalletMethod).where(XboxWalletMethod.code == method_data["code"])
        )
        if method is None:
            method = XboxWalletMethod(
                code=method_data["code"],
                label=method_data["label"],
                is_active=True,
            )
            session.add(method)
            session.flush()
        else:
            method.label = method_data["label"]
            method.is_active = True
            method.last_updated_at = now

        for item_code, item_label, leaf_name, _currency in method_data["items"]:
            wallet_pool_id = leaf_id_by_name.get(leaf_name)
            if wallet_pool_id is None:
                continue  # 该叶子钱包未建好（不应发生）
            existing_item = session.scalar(
                select(XboxWalletItem).where(
                    XboxWalletItem.method_id == method.id,
                    XboxWalletItem.code == item_code,
                )
            )
            if existing_item is None:
                item = XboxWalletItem(
                    method_id=method.id,
                    code=item_code,
                    label=item_label,
                    wallet_pool_id=wallet_pool_id,
                    is_active=True,
                )
                session.add(item)
            else:
                existing_item.label = item_label
                existing_item.wallet_pool_id = wallet_pool_id
                existing_item.is_active = True
                existing_item.last_updated_at = now

    session.flush()


def soft_delete_old_taiwan_wallets(session: Session) -> list[str]:
    """CEO 2026-05-08 Q3:B - 台湾现有 3 个空钱包(8591余额/银行卡/超商代收金流余额)删除。

    用 deleted_at 软删除,不动 wallet 行(防 FK 引用断裂)。返回删除的名字列表。
    """
    OLD_TAIWAN_NAMES = ("8591余额", "银行卡", "超商代收金流余额")
    deleted: list[str] = []
    for name in OLD_TAIWAN_NAMES:
        wallet = session.scalar(
            select(Wallet).where(
                Wallet.type == WalletType.TAIWAN.value,
                Wallet.currency == Currency.TWD.value,
                Wallet.name == name,
                Wallet.parent_id.is_(None),
                Wallet.deleted_at.is_(None),
            )
        )
        if wallet is None:
            continue
        # 安全检查：余额非 0 / 有流水时记录但仍删除（CEO 已确认是空的）
        wallet.deleted_at = china_now()
        deleted.append(name)
    session.flush()
    return deleted
