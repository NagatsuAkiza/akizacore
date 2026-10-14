from fastapi import APIRouter, Query

from akizacore.api.deps import ManagedServerDep, ServicesDep
from akizacore.schemas.ai_usage import ServerUsageReport

router = APIRouter(prefix="/servers", tags=["ai"])


@router.get(
    "/{server_id}/ai/usage",
    summary="Laporan pemakaian AI server",
    response_model=ServerUsageReport,
)
async def get_server_ai_usage(
    ctx: ManagedServerDep,
    services: ServicesDep,
    days: int = Query(7, ge=1, le=90, description="Rentang hari (termasuk hari ini)"),
) -> ServerUsageReport:
    return await services.usage.server_report(ctx.id, days=days)
