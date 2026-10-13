"""Format error seragam API: {"error": {"code": ..., "message": ...}}."""

from collections.abc import Mapping
from http import HTTPStatus

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from akizacore.core.exceptions import (
    AkizaError,
    InsufficientFunds,
    NotFound,
    PermissionDenied,
    ProviderUnavailable,
    QuotaExceeded,
    ValidationFailed,
)

log = structlog.get_logger()

# Urutan penting: subclass lebih dulu. AkizaError dasar menjadi fallback.
_DOMAIN_CODES: tuple[tuple[type[AkizaError], str], ...] = (
    (NotFound, "not_found"),
    (ValidationFailed, "validation_failed"),
    (PermissionDenied, "forbidden"),
    (InsufficientFunds, "insufficient_funds"),
    (QuotaExceeded, "quota_exceeded"),
    (ProviderUnavailable, "provider_unavailable"),
)
_HTTP_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    429: "too_many_requests",
    503: "service_unavailable",
}
# Pesan bawaan Starlette/FastAPI (Inggris) diganti agar konsisten dengan pesan domain.
_HTTP_MESSAGES = {
    400: "Permintaan tidak valid.",
    401: "Kamu belum login.",
    403: "Kamu tidak punya izin untuk ini.",
    404: "Endpoint tidak ditemukan.",
    405: "Metode HTTP tidak didukung untuk endpoint ini.",
    409: "Terjadi konflik data.",
    429: "Terlalu banyak permintaan, coba lagi nanti.",
    503: "Layanan sedang tidak tersedia.",
}
INTERNAL_MESSAGE = "Terjadi kesalahan pada server."


def error_body(code: str, message: str) -> dict[str, dict[str, str]]:
    return {"error": {"code": code, "message": message}}


def error_response(
    status_code: int, code: str, message: str, headers: Mapping[str, str] | None = None
) -> JSONResponse:
    return JSONResponse(error_body(code, message), status_code=status_code, headers=headers)


def domain_code(exc: AkizaError) -> str:
    for cls, code in _DOMAIN_CODES:
        if isinstance(exc, cls):
            return code
    return "error"


async def _akiza_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AkizaError)
    return error_response(exc.http_status, domain_code(exc), exc.user_message)


async def _validation_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    parts = [
        f"{'.'.join(str(p) for p in e['loc'][1:]) or e['loc'][0]}: {e['msg']}"
        for e in exc.errors()[:3]
    ]
    message = "Input tidak valid"
    if parts:
        message += ": " + "; ".join(parts)
    return error_response(422, "validation_error", message[:300])


async def _http_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    code = _HTTP_CODES.get(exc.status_code, "http_error")
    default = HTTPStatus(exc.status_code).phrase if exc.status_code in _HTTP_CODES else ""
    if isinstance(exc.detail, str) and exc.detail and exc.detail != default:
        message = exc.detail  # pesan sengaja dari kode kita
    else:
        message = _HTTP_MESSAGES.get(exc.status_code, code)
    return error_response(exc.status_code, code, message, headers=exc.headers)


async def _unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    # Detail hanya ke log, tidak pernah ke klien.
    log.error("api_unhandled_error", path=request.url.path, exc_info=exc)
    return error_response(500, "internal_error", INTERNAL_MESSAGE)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AkizaError, _akiza_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(Exception, _unhandled_error)
