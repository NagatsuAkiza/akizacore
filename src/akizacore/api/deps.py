from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncEngine

from akizacore.services.container import Services


def get_services(request: Request) -> Services:
    """Service layer yang sama dengan bot. Router tidak boleh query database sendiri."""
    services: Services = request.app.state.services
    return services


def get_engine(request: Request) -> AsyncEngine:
    engine: AsyncEngine = request.app.state.engine
    return engine


ServicesDep = Annotated[Services, Depends(get_services)]
EngineDep = Annotated[AsyncEngine, Depends(get_engine)]
