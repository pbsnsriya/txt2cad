"""FastAPI entry point. Run: python -m app.main  (binds 127.0.0.1 only)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config
from .api.routes import router
from .db import repo


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    repo.init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="txt2cad", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=config.ALLOWED_ORIGINS, allow_methods=["*"], allow_headers=["*"])
    app.include_router(router)
    return app


app = create_app()

if __name__ == "__main__":
    uvicorn.run(app, host=config.HOST, port=config.PORT, log_level="info")
