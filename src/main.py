"""Finance system API application."""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def _load_dotenv_basic() -> None:
    """简单读 .env 到 os.environ（不依赖 python-dotenv,只支持 KEY=VALUE 格式）。

    项目根目录的 .env 已 .gitignore。XBOX_ACCOUNT_PASSWORD_KEY 等敏感配置走这。
    """
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        value = value.strip()
        # 不覆盖已存在的环境变量(允许 export 优先)
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv_basic()


from src import database  # noqa: E402  必须在 _load_dotenv_basic 之后
from src.routers.assets import router as assets_router
from src.routers.operator import router as operator_router
from src.routers.vendors import router as vendors_router
from src.routers.xbox import router as xbox_router
from src.routers.taobao import router as taobao_router
from src.routers.taiwan import router as taiwan_router
from src.routers.transfers import router as transfers_router
from src.services.assets import ensure_default_asset_wallets
from src.services.taiwan import ensure_default_taiwan_wallets
from src.services.taobao import ensure_default_taobao_wallets
from src.services.vendors import ensure_vendor_wallets
from src.services.taobao import ensure_shop_total_group_wallets
from src.services.xbox_sales_ledger import (
    ensure_xbox_default_reconcile_mappings,
    ensure_xbox_default_wallet_settings,
    ensure_xbox_sales_ledger_wallets,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    database.init_db()
    db = database.SessionLocal()
    try:
        ensure_default_asset_wallets(db)
        ensure_default_taobao_wallets(db)
        ensure_default_taiwan_wallets(db)
        ensure_vendor_wallets(db)
        # CEO 2026-05-17: 旧的 soft_delete_old_taiwan_wallets 已弃用 —
        # 它会误删新的"银行卡" group(同名). 台湾钱包结构改造后不再需要.
        leaf_id_by_name = ensure_xbox_sales_ledger_wallets(db)
        ensure_xbox_default_wallet_settings(db, leaf_id_by_name)
        # 淘宝店铺总钱包(group) + 自动配对账映射(CEO 2026-05-08 B+A)
        ensure_shop_total_group_wallets(db)
        ensure_xbox_default_reconcile_mappings(db)
        db.commit()
    finally:
        db.close()
    yield


app = FastAPI(title="Finance System API", lifespan=lifespan)

# CEO 2026-05-14: 允许前端 (Next.js dev :3000 / :3100, Electron file://)
# 直连后端,绕过 Next.js dev proxy 的 30s 默认超时 (Playwright 同步可能
# 走到 60s+)。本地开发环境放开全部 origin,生产打包时再收紧。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,  # allow_origins="*" 时必须 False
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(assets_router)
app.include_router(operator_router)
app.include_router(vendors_router)
app.include_router(xbox_router)
app.include_router(taobao_router)
app.include_router(taiwan_router)
app.include_router(transfers_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
