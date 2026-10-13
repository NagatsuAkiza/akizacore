from typing import Any

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from akizacore.api.app import API_PREFIX, create_app
from akizacore.config import ApiSettings
from akizacore.schemas.discord import GuildInfo, UserInfo
from akizacore.schemas.settings import SettingsUpdate
from akizacore.services.container import Services


def make_settings(**kwargs: Any) -> ApiSettings:
    defaults: dict[str, Any] = {
        "discord_client_id": "123456789",
        "discord_client_secret": SecretStr("client_secret_xyz"),
        "discord_oauth_redirect_uri": "http://localhost:8000/api/v1/auth/discord/callback",
        "dashboard_url": "http://localhost:5173",
        "guild_cache_ttl_s": 60,
    }
    defaults.update(kwargs)
    return ApiSettings(**defaults)


def client_for(app: Any, cookies: dict[str, str] | None = None) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://test", cookies=cookies)


@pytest.fixture
def api_services(session_factory: async_sessionmaker[AsyncSession]) -> Services:
    return Services.build(session_factory)


ALL_SERVER_ENDPOINTS = [
    ("GET", ""),
    ("GET", "/settings"),
    ("PUT", "/settings"),
    ("GET", "/stats"),
    ("GET", "/economy/leaderboard"),
    ("GET", "/moderation/logs"),
    ("GET", "/moderation/warnings"),
    ("GET", "/warnings"),
]


@pytest.mark.parametrize("method,path_suffix", ALL_SERVER_ENDPOINTS)
async def test_server_endpoint_unauthenticated_returns_401(
    api_services: Services, method: str, path_suffix: str
) -> None:
    """Semua endpoint /servers/{id}/* wajib menolak request tanpa sesi (401)."""
    server_id = 999
    app = create_app(settings=make_settings(), services=api_services)

    async with client_for(app) as client:
        url = f"{API_PREFIX}/servers/{server_id}{path_suffix}"
        if method == "GET":
            response = await client.get(url)
        elif method == "PUT":
            response = await client.put(url, json={"prefix": "?"})
        else:
            pytest.fail(f"Method {method} tidak didukung")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


@pytest.mark.parametrize("method,path_suffix", ALL_SERVER_ENDPOINTS)
async def test_cross_server_access_returns_403(
    api_services: Services, method: str, path_suffix: str
) -> None:
    """User A (admin Server A) dilarang mengakses Server B (403)."""
    user_a_id = 5001
    server_a_id = 1001
    server_b_id = 1002

    # Daftarkan User A dan kedua server di DB bot
    await api_services.onboarding.ensure_user(UserInfo(id=user_a_id, username="admin_a"))
    await api_services.onboarding.register_guild(
        GuildInfo(id=server_a_id, name="Server A", owner_id=user_a_id)
    )
    await api_services.onboarding.register_guild(
        GuildInfo(id=server_b_id, name="Server B", owner_id=9999)
    )

    session = await api_services.auth.create_session(
        user_id=user_a_id,
        access_token="tok_user_a",
        ttl_s=3600,
    )

    # Mock Discord: User A hanya punya izin di Server A, Server B tidak ada di list guild-nya
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v10/users/@me/guilds":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": str(server_a_id),
                        "name": "Server A",
                        "owner": True,
                        "permissions": "0",
                    }
                ],
            )
        return httpx.Response(404)

    settings = make_settings()
    app = create_app(settings=settings, services=api_services)
    app.state.http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async with client_for(app, cookies={settings.session_cookie_name: session.id}) as client:
        url = f"{API_PREFIX}/servers/{server_b_id}{path_suffix}"
        if method == "GET":
            response = await client.get(url)
        elif method == "PUT":
            response = await client.put(url, json={"prefix": "?"})
        else:
            pytest.fail(f"Method {method} tidak didukung")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


@pytest.mark.parametrize("method,path_suffix", ALL_SERVER_ENDPOINTS)
async def test_insufficient_permissions_within_guild_returns_403(
    api_services: Services, method: str, path_suffix: str
) -> None:
    """User biasa tanpa Manage Server / Administrator dilarang mengakses endpoint (403)."""
    user_b_id = 5002
    server_b_id = 1002

    await api_services.onboarding.ensure_user(UserInfo(id=user_b_id, username="regular_user"))
    await api_services.onboarding.register_guild(
        GuildInfo(id=server_b_id, name="Server B", owner_id=9999)
    )

    session = await api_services.auth.create_session(
        user_id=user_b_id,
        access_token="tok_user_b",
        ttl_s=3600,
    )

    # Mock Discord: User B ada di Server B tapi tanpa permission Manage Server (0x20)
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v10/users/@me/guilds":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": str(server_b_id),
                        "name": "Server B",
                        "owner": False,
                        "permissions": "0",  # Tidak punya Manage Server
                    }
                ],
            )
        return httpx.Response(404)

    settings = make_settings()
    app = create_app(settings=settings, services=api_services)
    app.state.http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async with client_for(app, cookies={settings.session_cookie_name: session.id}) as client:
        url = f"{API_PREFIX}/servers/{server_b_id}{path_suffix}"
        if method == "GET":
            response = await client.get(url)
        elif method == "PUT":
            response = await client.put(url, json={"prefix": "?"})
        else:
            pytest.fail(f"Method {method} tidak didukung")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


@pytest.mark.parametrize("method,path_suffix", ALL_SERVER_ENDPOINTS)
async def test_inactive_bot_server_returns_404(
    api_services: Services, method: str, path_suffix: str
) -> None:
    """User punya Manage Server, tetapi bot tidak aktif di server tersebut (404)."""
    user_id = 5003
    server_c_id = 1003

    await api_services.onboarding.ensure_user(UserInfo(id=user_id, username="admin_c"))
    # Daftarkan lalu nonaktifkan bot di server C
    await api_services.onboarding.register_guild(
        GuildInfo(id=server_c_id, name="Server C", owner_id=user_id)
    )
    await api_services.onboarding.deactivate_guild(server_c_id)

    session = await api_services.auth.create_session(
        user_id=user_id,
        access_token="tok_user_c",
        ttl_s=3600,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v10/users/@me/guilds":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": str(server_c_id),
                        "name": "Server C",
                        "owner": True,
                        "permissions": "0",
                    }
                ],
            )
        return httpx.Response(404)

    settings = make_settings()
    app = create_app(settings=settings, services=api_services)
    app.state.http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async with client_for(app, cookies={settings.session_cookie_name: session.id}) as client:
        url = f"{API_PREFIX}/servers/{server_c_id}{path_suffix}"
        if method == "GET":
            response = await client.get(url)
        elif method == "PUT":
            response = await client.put(url, json={"prefix": "?"})
        else:
            pytest.fail(f"Method {method} tidak didukung")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_multi_tenant_data_isolation(api_services: Services) -> None:
    """Verifikasi isolasi data ketat: data Server 1 tidak boleh bocor ke Server 2 dan sebaliknya."""
    user1_id = 6001
    user2_id = 6002
    server1_id = 2001
    server2_id = 2002

    # 1. Onboarding users & servers
    await api_services.onboarding.ensure_user(UserInfo(id=user1_id, username="admin_one"))
    await api_services.onboarding.ensure_user(UserInfo(id=user2_id, username="admin_two"))
    await api_services.onboarding.register_guild(
        GuildInfo(id=server1_id, name="Server One", owner_id=user1_id)
    )
    await api_services.onboarding.register_guild(
        GuildInfo(id=server2_id, name="Server Two", owner_id=user2_id)
    )

    # 2. Setup Server 1 data
    await api_services.settings.update(server1_id, SettingsUpdate(prefix="!"))
    await api_services.economy.credit(server1_id, user1_id, 1000, kind="daily")
    await api_services.moderation.warn(
        server_id=server1_id, user_id=user1_id, mod_id=user1_id, reason="Warning in S1"
    )
    await api_services.moderation.log_action(
        server_id=server1_id,
        target_id=user1_id,
        mod_id=user1_id,
        action="kick",
        reason="Kick in S1",
    )

    # 3. Setup Server 2 data
    await api_services.settings.update(server2_id, SettingsUpdate(prefix="?"))
    await api_services.economy.credit(server2_id, user2_id, 2000, kind="daily")
    await api_services.moderation.warn(
        server_id=server2_id, user_id=user2_id, mod_id=user2_id, reason="Warning in S2"
    )
    await api_services.moderation.log_action(
        server_id=server2_id,
        target_id=user2_id,
        mod_id=user2_id,
        action="ban",
        reason="Ban in S2",
    )

    # 4. Sesi untuk User 1 dan User 2
    session1 = await api_services.auth.create_session(
        user_id=user1_id, access_token="tok_s1", ttl_s=3600
    )
    session2 = await api_services.auth.create_session(
        user_id=user2_id, access_token="tok_s2", ttl_s=3600
    )

    def discord_handler(request: httpx.Request) -> httpx.Response:
        auth = request.headers.get("Authorization", "")
        if "tok_s1" in auth:
            return httpx.Response(
                200,
                json=[
                    {"id": str(server1_id), "name": "Server One", "owner": True, "permissions": "0"}
                ],
            )
        if "tok_s2" in auth:
            return httpx.Response(
                200,
                json=[
                    {"id": str(server2_id), "name": "Server Two", "owner": True, "permissions": "0"}
                ],
            )
        return httpx.Response(401)

    settings = make_settings()
    app = create_app(settings=settings, services=api_services)
    app.state.http_client = httpx.AsyncClient(transport=httpx.MockTransport(discord_handler))

    # --- Pengujian User 1 mengakses Server 1 ---
    async with client_for(app, cookies={settings.session_cookie_name: session1.id}) as c1:
        # Settings
        r_settings = await c1.get(f"{API_PREFIX}/servers/{server1_id}/settings")
        assert r_settings.status_code == 200
        assert r_settings.json()["prefix"] == "!"

        # Leaderboard: hanya user1, bukan user2
        r_lead = await c1.get(f"{API_PREFIX}/servers/{server1_id}/economy/leaderboard")
        assert r_lead.status_code == 200
        lead_data = r_lead.json()
        assert lead_data["total"] == 1
        assert lead_data["items"][0]["username"] == "admin_one"
        assert lead_data["items"][0]["balance"] == 1100  # 100 starter + 1000

        # Mod logs: hanya log S1 (warn & kick, tidak ada ban dari S2)
        r_logs = await c1.get(f"{API_PREFIX}/servers/{server1_id}/moderation/logs")
        assert r_logs.status_code == 200
        logs_data = r_logs.json()
        assert logs_data["total"] == 2
        assert {i["action"] for i in logs_data["items"]} == {"warn", "kick"}

        # Warnings: hanya warning S1
        r_warn = await c1.get(f"{API_PREFIX}/servers/{server1_id}/moderation/warnings")
        assert r_warn.status_code == 200
        warn_data = r_warn.json()
        assert warn_data["total"] == 1
        assert warn_data["items"][0]["reason"] == "Warning in S1"

        # Coba akses Server 2 -> langsung 403 Forbidden
        r_cross = await c1.get(f"{API_PREFIX}/servers/{server2_id}/settings")
        assert r_cross.status_code == 403

    # --- Pengujian User 2 mengakses Server 2 ---
    async with client_for(app, cookies={settings.session_cookie_name: session2.id}) as c2:
        # Settings
        r_settings = await c2.get(f"{API_PREFIX}/servers/{server2_id}/settings")
        assert r_settings.status_code == 200
        assert r_settings.json()["prefix"] == "?"

        # Leaderboard: hanya user2, bukan user1
        r_lead = await c2.get(f"{API_PREFIX}/servers/{server2_id}/economy/leaderboard")
        assert r_lead.status_code == 200
        lead_data = r_lead.json()
        assert lead_data["total"] == 1
        assert lead_data["items"][0]["username"] == "admin_two"
        assert lead_data["items"][0]["balance"] == 2100  # 100 starter + 2000

        # Mod logs: hanya log S2 (warn & ban, tidak ada kick dari S1)
        r_logs = await c2.get(f"{API_PREFIX}/servers/{server2_id}/moderation/logs")
        assert r_logs.status_code == 200
        logs_data = r_logs.json()
        assert logs_data["total"] == 2
        assert {i["action"] for i in logs_data["items"]} == {"warn", "ban"}

        # Warnings: hanya warning S2
        r_warn = await c2.get(f"{API_PREFIX}/servers/{server2_id}/moderation/warnings")
        assert r_warn.status_code == 200
        warn_data = r_warn.json()
        assert warn_data["total"] == 1
        assert warn_data["items"][0]["reason"] == "Warning in S2"

        # Coba akses Server 1 -> langsung 403 Forbidden
        r_cross = await c2.get(f"{API_PREFIX}/servers/{server1_id}/settings")
        assert r_cross.status_code == 403
