"""FastAPI entry point. Run: python -m app.main  (binds 127.0.0.1 only)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import uvicorn
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
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

    @app.exception_handler(RequestValidationError)
    async def validation_message(_: Request, exc: RequestValidationError) -> JSONResponse:
        """A readable one-line reason (the default is a list of objects, which a UI cannot show)."""
        first = exc.errors()[0]
        field = ".".join(str(p) for p in first["loc"] if p != "body")
        return JSONResponse(status_code=422, content={"detail": f"{field}: {first['msg']}" if field else first["msg"]})

    return app


app = create_app()

if __name__ == "__main__":
    uvicorn.run(app, host=config.HOST, port=config.PORT, log_level="info")
