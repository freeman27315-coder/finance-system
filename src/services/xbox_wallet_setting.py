"""XBOX 钱包设置同步服务（FR-03）。

财务系统通过 PUT /xbox/wallet-settings 推送 method/item 三层映射,
XBOX 模块只消费,不在 XBOX 内单独维护资金池规则。

数据结构：
  收款方式 (method)
    └─ 备注模板 (item) → 资金池 (wallet_pool_id, 即 wallets.id)

同步语义：
- 推送过来的 method/item 全量替换式同步:
  - 已存在的(按 code) → 更新 label / wallet_pool_id / is_active
  - 不在推送列表里的现有项 → is_active=False（保留历史关联）
- 删除/停用的 item 在订单补齐页下拉框不可选,但历史销售记录的 walletPoolId 不被改写
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.wallet import Wallet
from src.models.xbox import XboxWalletItem, XboxWalletMethod
from src.utils.time import china_now


def upsert_wallet_settings(session: Session, payload: list[dict]) -> dict:
    """全量同步 method/item 树。

    payload 格式：
        [
          {
            "code": "agent",
            "label": "代理",
            "items": [
              {"code": "001", "label": "代理 001", "walletPoolId": 12, "isActive": true},
              ...
            ]
          },
          ...
        ]

    返回简单计数 ``{methods_upserted, items_upserted, items_disabled}``。
    """
    incoming_method_codes = {m["code"] for m in payload}
    incoming_item_codes_per_method: dict[str, set[str]] = {
        m["code"]: {it["code"] for it in m.get("items", [])} for m in payload
    }

    methods_upserted = 0
    items_upserted = 0
    items_disabled = 0
    now = china_now()

    for method_data in payload:
        method = session.scalar(
            select(XboxWalletMethod).where(XboxWalletMethod.code == method_data["code"])
        )
        if method is None:
            method = XboxWalletMethod(
                code=method_data["code"],
                label=method_data["label"],
                is_active=method_data.get("isActive", True),
            )
            session.add(method)
            session.flush()
        else:
            method.label = method_data["label"]
            method.is_active = method_data.get("isActive", True)
            method.last_updated_at = now
        methods_upserted += 1

        for item_data in method_data.get("items", []):
            wallet_pool_id = item_data["walletPoolId"]
            wallet = session.get(Wallet, wallet_pool_id)
            if wallet is None:
                raise ValueError(f"walletPoolId {wallet_pool_id} 对应的钱包不存在")

            item = session.scalar(
                select(XboxWalletItem).where(
                    XboxWalletItem.method_id == method.id,
                    XboxWalletItem.code == item_data["code"],
                )
            )
            if item is None:
                item = XboxWalletItem(
                    method_id=method.id,
                    code=item_data["code"],
                    label=item_data["label"],
                    wallet_pool_id=wallet_pool_id,
                    is_active=item_data.get("isActive", True),
                )
                session.add(item)
            else:
                item.label = item_data["label"]
                item.wallet_pool_id = wallet_pool_id
                item.is_active = item_data.get("isActive", True)
                item.last_updated_at = now
            items_upserted += 1

    # 不在推送列表的现有 method 全部 is_active=False（保留历史关联）
    existing_methods = list(session.scalars(select(XboxWalletMethod)))
    for m in existing_methods:
        if m.code not in incoming_method_codes:
            m.is_active = False
            m.last_updated_at = now
        else:
            # 该 method 内不在推送列表的 item 也 disable
            existing_items = list(
                session.scalars(select(XboxWalletItem).where(XboxWalletItem.method_id == m.id))
            )
            keep = incoming_item_codes_per_method.get(m.code, set())
            for it in existing_items:
                if it.code not in keep:
                    if it.is_active:
                        items_disabled += 1
                    it.is_active = False
                    it.last_updated_at = now

    session.flush()
    return {
        "methods_upserted": methods_upserted,
        "items_upserted": items_upserted,
        "items_disabled": items_disabled,
    }


def list_wallet_methods(session: Session, only_active: bool = True) -> list[XboxWalletMethod]:
    stmt = select(XboxWalletMethod).order_by(XboxWalletMethod.id)
    if only_active:
        stmt = stmt.where(XboxWalletMethod.is_active.is_(True))
    return list(session.scalars(stmt))


def get_item_or_404(session: Session, item_id: int) -> Optional[XboxWalletItem]:
    return session.get(XboxWalletItem, item_id)
