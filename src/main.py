"""Finance system API application."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from src import database
from src.routers.assets import router as assets_router
from src.routers.vendors import router as vendors_router
from src.routers.xbox import router as xbox_router
from src.services.assets import ensure_default_asset_wallets


@asynccontextmanager
async def lifespan(_: FastAPI):
    database.init_db()
    db = database.SessionLocal()
    try:
        ensure_default_asset_wallets(db)
        db.commit()
    finally:
        db.close()
    yield


app = FastAPI(title="Finance System API", lifespan=lifespan)
app.include_router(assets_router)
app.include_router(vendors_router)
app.include_router(xbox_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
