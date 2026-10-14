from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from akizacore.api.app import API_PREFIX, create_app
from akizacore.config import ApiSettings
from akizacore.database.repositories import AIUsageRepository
from akizacore.database.session import session_scope
from akizacore.schemas.discord import GuildInfo, UserInfo
from akizacore.services.container import Services


def make_settings() -> ApiSettings:
    return ApiSettings(
        discord_client_id="123456789",
        discord_client_secret=SecretStr("client_secret_xyz"),
        discord_oauth_redirect_uri="http://localhost:8000/api/v1/auth/discord/callback",
        dashboard_url="http://localhost:5173",
        guild_cache_ttl_s=60,
    )


def client_for(app: Any, cookies: dict[str, str] | None = None) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://test", cookies=cookies)


@pytest.fixture
def api_services(session_factory: async_sessionmaker[AsyncSession]) -> Services:
    return Services.build(session_factory)


async def build_app(
    services: Services, *, user_id: int, server_id: int, owner: bool, permissions: str
) -> tuple[FastAPI, str]:
    await services.onboarding.ensure_user(UserInfo(id=user_id, username="usage_admin"))
    await services.onboarding.register_guild(
        GuildInfo(id=server_id, name="Usage Guild", owner_id=user_id)
    )
    session = await services.auth.create_session(
        user_id=user_id, access_token="tok_usage", ttl_s=3600
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v10/users/@me/guilds":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": str(server_id),
                        "name": "Usage Guild",
                        "owner": owner,
                        "permissions": permissions,
                    }
                ],
            )
        return httpx.Response(404)

    settings = make_settings()
    app = create_app(settings=settings, services=services)
    app.state.http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return app, session.id


async def seed(services: Services, session_factory_: Any, server_id: int, user_id: int) -> None:
    async with session_scope(session_factory_) as session:
        await AIUsageRepository(session).add(
            server_id=server_id,
            user_id=user_id,
            model="m1",
            prompt_tokens=10,
            completion_tokens=5,
            coins=5,
            latency_ms=120,
            tools=("get_balance",),
        )


async def test_ai_usage_requires_login(api_services: Services) -> None:
    app = create_app(settings=make_settings(), services=api_services)
    async with client_for(app) as client:
        response = await client.get(f"{API_PREFIX}/servers/701/ai/usage")
    assert response.status_code == 401


async def test_ai_usage_returns_report_for_manager(
    api_services: Services, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    user_id, server_id = 333001, 701
    app, session_id = await build_app(
        api_services, user_id=user_id, server_id=server_id, owner=True, permissions="0"
    )
    await seed(api_services, session_factory, server_id, user_id)

    cookie = make_settings().session_cookie_name
    async with client_for(app, cookies={cookie: session_id}) as client:
        response = await client.get(f"{API_PREFIX}/servers/{server_id}/ai/usage?days=3")

    assert response.status_code == 200
    data = response.json()
    assert data["days"] == 3
    assert data["totals"]["requests"] == 1
    assert data["totals"]["prompt_tokens"] == 10
    assert len(data["daily"]) == 3
    assert data["daily"][-1]["requests"] == 1
    assert data["top_users"][0]["user_id"] == str(user_id)
    assert data["tools"][0] == {"name": "get_balance", "requests": 1, "tokens": 0}
    assert data["recent_errors"] == []


async def test_ai_usage_forbidden_for_non_manager(api_services: Services) -> None:
    user_id, server_id = 333002, 702
    app, session_id = await build_app(
        api_services, user_id=user_id, server_id=server_id, owner=False, permissions="1"
    )
    cookie = make_settings().session_cookie_name
    async with client_for(app, cookies={cookie: session_id}) as client:
        response = await client.get(f"{API_PREFIX}/servers/{server_id}/ai/usage")
    assert response.status_code == 403


@pytest.mark.parametrize("days", [0, 91])
async def test_ai_usage_validates_days(api_services: Services, days: int) -> None:
    user_id, server_id = 333003, 703
    app, session_id = await build_app(
        api_services, user_id=user_id, server_id=server_id, owner=True, permissions="0"
    )
    cookie = make_settings().session_cookie_name
    async with client_for(app, cookies={cookie: session_id}) as client:
        response = await client.get(f"{API_PREFIX}/servers/{server_id}/ai/usage?days={days}")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
