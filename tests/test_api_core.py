"""Fondasi API Fase 6: format error seragam, health check, CORS, dan dependency service."""

from collections.abc import AsyncIterator
from typing import Annotated

import httpx
import pytest
from fastapi import FastAPI, Query
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from akizacore.api.app import API_PREFIX, create_app
from akizacore.api.deps import ServicesDep
from akizacore.config import ApiSettings
from akizacore.core.exceptions import (
    AkizaError,
    InsufficientFunds,
    NotFound,
    PermissionDenied,
    ProviderUnavailable,
    QuotaExceeded,
    ValidationFailed,
)
from akizacore.services.container import Services

Factory = async_sessionmaker[AsyncSession]
ORIGIN = "http://localhost:5173"
UNREACHABLE_DB = "postgresql+asyncpg://nobody:nobody@127.0.0.1:1/none"


class Teapot(AkizaError):
    user_message = "Aku teko."
    http_status = 418


def client_for(app: FastAPI) -> httpx.AsyncClient:
    # raise_app_exceptions=False: error tak tertangani harus tampil sebagai respons 500, bukan raise
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


def add_test_routes(app: FastAPI) -> None:
    errors: dict[str, Exception] = {
        "not_found": NotFound(),
        "validation_failed": ValidationFailed("Nilai salah."),
        "forbidden": PermissionDenied(),
        "insufficient_funds": InsufficientFunds(),
        "quota_exceeded": QuotaExceeded(),
        "provider_unavailable": ProviderUnavailable("detail internal rahasia"),
        "error": Teapot(),
        "internal_error": RuntimeError("rahasia: password=hunter2"),
    }

    @app.get("/boom/{kind}")
    async def boom(kind: str) -> None:
        raise errors[kind]

    @app.get("/limited")
    async def limited(limit: Annotated[int, Query(le=100)] = 10) -> dict[str, int]:
        return {"limit": limit}

    @app.get("/whoami")
    async def whoami(services: ServicesDep) -> dict[str, bool]:
        return {"has_economy": services.economy is not None}


@pytest.fixture
async def app(session_factory: Factory) -> AsyncIterator[FastAPI]:
    engine = session_factory.kw["bind"]
    assert isinstance(engine, AsyncEngine)
    application = create_app(ApiSettings(), engine=engine, services=Services.build(session_factory))
    add_test_routes(application)
    yield application


# ---------- Format error seragam ----------
@pytest.mark.parametrize(
    ("kind", "status", "code", "message"),
    [
        ("not_found", 404, "not_found", "Data tidak ditemukan."),
        ("validation_failed", 400, "validation_failed", "Nilai salah."),
        ("forbidden", 403, "forbidden", "Kamu tidak punya izin untuk ini."),
        ("insufficient_funds", 400, "insufficient_funds", "Koin kamu tidak cukup."),
        ("quota_exceeded", 429, "quota_exceeded", "Kuota habis, coba lagi nanti."),
        (
            "provider_unavailable",
            503,
            "provider_unavailable",
            "AI sedang tidak tersedia, coba lagi nanti.",
        ),
        ("error", 418, "error", "Aku teko."),
    ],
)
async def test_domain_errors_map_to_http_with_uniform_body(
    app: FastAPI, kind: str, status: int, code: str, message: str
) -> None:
    async with client_for(app) as client:
        response = await client.get(f"/boom/{kind}")
    assert response.status_code == status
    assert response.json() == {"error": {"code": code, "message": message}}


async def test_unhandled_error_is_500_and_never_leaks_details(app: FastAPI) -> None:
    async with client_for(app) as client:
        response = await client.get("/boom/internal_error")
    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "internal_error"
    assert "hunter2" not in response.text and "rahasia" not in response.text


async def test_provider_detail_is_not_exposed(app: FastAPI) -> None:
    async with client_for(app) as client:
        response = await client.get("/boom/provider_unavailable")
    assert "rahasia" not in response.text


async def test_request_validation_error_uses_uniform_body(app: FastAPI) -> None:
    async with client_for(app) as client:
        response = await client.get("/limited", params={"limit": 500})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["message"].startswith("Input tidak valid")
    assert "limit" in error["message"]
    assert set(response.json()) == {"error"}


async def test_unknown_path_and_wrong_method_use_uniform_body(app: FastAPI) -> None:
    async with client_for(app) as client:
        missing = await client.get("/tidak-ada")
        wrong = await client.post(f"{API_PREFIX}/health")
    assert missing.status_code == 404
    assert missing.json() == {
        "error": {"code": "not_found", "message": "Endpoint tidak ditemukan."}
    }
    assert wrong.status_code == 405
    assert wrong.json()["error"]["code"] == "method_not_allowed"
    assert "tidak didukung" in wrong.json()["error"]["message"]


# ---------- Health ----------
async def test_health_is_alive_without_database() -> None:
    app = create_app(ApiSettings(), engine=create_async_engine(UNREACHABLE_DB))
    async with client_for(app) as client:
        response = await client.get(f"{API_PREFIX}/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_ready_ok_when_database_reachable(app: FastAPI) -> None:
    async with client_for(app) as client:
        response = await client.get(f"{API_PREFIX}/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_ready_503_when_database_unreachable() -> None:
    app = create_app(ApiSettings(), engine=create_async_engine(UNREACHABLE_DB))
    async with client_for(app) as client:
        response = await client.get(f"{API_PREFIX}/health/ready")
    assert response.status_code == 503
    assert response.json() == {
        "error": {"code": "service_unavailable", "message": "Database tidak dapat dijangkau."}
    }
    assert "nobody" not in response.text and "127.0.0.1" not in response.text


# ---------- OpenAPI / docs ----------
async def test_openapi_lists_health_routes(app: FastAPI) -> None:
    async with client_for(app) as client:
        response = await client.get(f"{API_PREFIX}/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert f"{API_PREFIX}/health" in paths and f"{API_PREFIX}/health/ready" in paths


async def test_docs_only_in_dev() -> None:
    dev = create_app(ApiSettings(environment="dev"), engine=create_async_engine(UNREACHABLE_DB))
    prod = create_app(ApiSettings(environment="prod"), engine=create_async_engine(UNREACHABLE_DB))
    async with client_for(dev) as client:
        assert (await client.get(f"{API_PREFIX}/docs")).status_code == 200
    async with client_for(prod) as client:
        assert (await client.get(f"{API_PREFIX}/docs")).status_code == 404
        assert (await client.get(f"{API_PREFIX}/openapi.json")).status_code == 200


# ---------- CORS ----------
async def test_cors_allows_dashboard_origin_with_credentials(app: FastAPI) -> None:
    async with client_for(app) as client:
        response = await client.options(
            f"{API_PREFIX}/health",
            headers={"Origin": ORIGIN, "Access-Control-Request-Method": "GET"},
        )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == ORIGIN
    assert response.headers["access-control-allow-credentials"] == "true"


async def test_cors_rejects_other_origins(app: FastAPI) -> None:
    async with client_for(app) as client:
        response = await client.get(
            f"{API_PREFIX}/health", headers={"Origin": "https://evil.example"}
        )
    assert "access-control-allow-origin" not in response.headers


def test_wildcard_origin_is_rejected_by_settings() -> None:
    with pytest.raises(ValidationError, match="DASHBOARD_ORIGINS"):
        ApiSettings(dashboard_origins=["*"])


def test_trailing_slash_is_normalized_in_origins() -> None:
    assert ApiSettings(dashboard_origins=[f"{ORIGIN}/"]).dashboard_origins == [ORIGIN]


# ---------- Dependency ----------
async def test_services_dependency_returns_injected_services(app: FastAPI) -> None:
    async with client_for(app) as client:
        response = await client.get("/whoami")
    assert response.json() == {"has_economy": True}
