import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from akizacore.api.deps import EngineDep

log = structlog.get_logger()
router = APIRouter(tags=["health"])


class HealthStatus(BaseModel):
    status: str


@router.get("/health", summary="Liveness: proses API hidup")
async def health() -> HealthStatus:
    return HealthStatus(status="ok")


@router.get("/health/ready", summary="Readiness: database dapat dijangkau")
async def ready(engine: EngineDep) -> HealthStatus:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        log.warning("api_database_unreachable", exc_info=True)
        raise HTTPException(status_code=503, detail="Database tidak dapat dijangkau.") from None
    return HealthStatus(status="ok")
