from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncEngine

from akizacore.api.errors import register_error_handlers
from akizacore.api.routers import health
from akizacore.config import ApiSettings
from akizacore.database.engine import build_engine, build_session_factory
from akizacore.services.container import Services

API_PREFIX = "/api/v1"


def create_app(
    settings: ApiSettings | None = None,
    *,
    engine: AsyncEngine | None = None,
    services: Services | None = None,
) -> FastAPI:
    """Bangun app FastAPI.

    Engine dibuat lazy (tidak membuka koneksi sampai dipakai). `engine`/`services` bisa
    disuntik untuk test. API memakai service layer yang sama dengan bot, tanpa provider AI.
    """
    cfg = settings or ApiSettings()
    owns_engine = engine is None
    engine = engine or build_engine(cfg.database_url)
    services = services or Services.build(build_session_factory(engine))

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        if owns_engine:
            await engine.dispose()

    dev = cfg.environment == "dev"
    app = FastAPI(
        title="AkizaCore API",
        version="0.1.0",
        lifespan=lifespan,
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs" if dev else None,
        redoc_url=None,
    )
    app.state.settings = cfg
    app.state.engine = engine
    app.state.services = services

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.dashboard_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type"],
    )
    register_error_handlers(app)
    app.include_router(health.router, prefix=API_PREFIX)
    return app


app = create_app()
