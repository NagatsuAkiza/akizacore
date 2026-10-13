from typing import Annotated

import httpx
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncEngine

from akizacore.config import ApiSettings
from akizacore.core.exceptions import Unauthorized
from akizacore.models import User
from akizacore.services.container import Services


def get_services(request: Request) -> Services:
    """Service layer yang sama dengan bot. Router tidak boleh query database sendiri."""
    services: Services = request.app.state.services
    return services


def get_engine(request: Request) -> AsyncEngine:
    engine: AsyncEngine = request.app.state.engine
    return engine


def get_settings(request: Request) -> ApiSettings:
    settings: ApiSettings = request.app.state.settings
    return settings


def get_http_client(request: Request) -> httpx.AsyncClient | None:
    return getattr(request.app.state, "http_client", None)


ServicesDep = Annotated[Services, Depends(get_services)]
EngineDep = Annotated[AsyncEngine, Depends(get_engine)]
SettingsDep = Annotated[ApiSettings, Depends(get_settings)]
HttpClientDep = Annotated[httpx.AsyncClient | None, Depends(get_http_client)]


async def get_current_user(
    request: Request,
    services: ServicesDep,
    settings: SettingsDep,
) -> User:
    session_id = request.cookies.get(settings.session_cookie_name)
    if not session_id:
        raise Unauthorized()
    user = await services.auth.get_user_by_session(session_id)
    if user is None:
        raise Unauthorized()
    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]
