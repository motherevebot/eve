import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from fastapi.staticfiles import StaticFiles

from app.api.accounting import router as accounting_router
from app.api.auth import router as auth_router
from app.api.bots import router as bots_router
from app.api.public import router as public_router
from app.api.metadata import router as metadata_router
from app.api.reports import router as reports_router
from app.api.upload import router as upload_router
from app.config import settings
from app.db.base import Base
from app.db.session import engine

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")

_scheduler_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _scheduler_task

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Start background scheduler
    from app.workers.scheduler import start_scheduler
    _scheduler_task = asyncio.create_task(start_scheduler())

    yield

    # Shutdown
    if _scheduler_task:
        _scheduler_task.cancel()
    try:
        from app.services.redis_store import close_redis
        await close_redis()
    except Exception:
        pass
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(bots_router)
app.include_router(accounting_router)
app.include_router(reports_router)
app.include_router(metadata_router)
app.include_router(upload_router)
app.include_router(public_router)

import os
_uploads_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
os.makedirs(_uploads_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=_uploads_dir), name="uploads")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "eve-api"}
