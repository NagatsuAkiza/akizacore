from typing import Any

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from akizacore.api.app import API_PREFIX, create_app
from akizacore.config import ApiSettings
from akizacore.schemas.discord import GuildInfo, UserInfo
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


# ---------- GET /servers ----------


async def test_servers_unauthenticated_returns_401(api_services: Services) -> None:
    app = create_app(settings=make_settings(), services=api_services)
    async with client_for(app) as client:
        response = await client.get(f"{API_PREFIX}/servers")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_servers_with_expired_session_returns_401(api_services: Services) -> None:
    user_id = 12345
    await api_services.onboarding.ensure_user(UserInfo(id=user_id, username="test_user"))
    session = await api_services.auth.create_session(
        user_id=user_id,
        access_token="tok_expired",
        ttl_s=-10,  # kedaluwarsa
    )

    settings = make_settings()
    app = create_app(settings=settings, services=api_services)
    async with client_for(app, cookies={settings.session_cookie_name: session.id}) as client:
        response = await client.get(f"{API_PREFIX}/servers")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_servers_list_filters_manageable_and_sets_bot_active(
    api_services: Services,
) -> None:
    user_id = 999111
    await api_services.onboarding.ensure_user(UserInfo(id=user_id, username="admin_user"))
    session = await api_services.auth.create_session(
        user_id=user_id,
        access_token="tok_guilds",
        ttl_s=3600,
    )

    # 1. Siapkan server di DB:
    # Guild 101: aktif
    await api_services.onboarding.register_guild(
        GuildInfo(id=101, name="Owner Server", owner_id=user_id)
    )
    # Guild 102: dinonaktifkan
    await api_services.onboarding.register_guild(
        GuildInfo(id=102, name="Admin Server", owner_id=8888)
    )
    await api_services.onboarding.deactivate_guild(102)
    # Guild 103: belum ada bot (tidak terdaftar di DB)

    discord_guilds = [
        {
            "id": "101",
            "name": "Owner Server",
            "icon": "icon_101",
            "owner": True,
            "permissions": "0",
        },
        {
            "id": "102",
            "name": "Admin Server",
            "icon": "icon_102",
            "owner": False,
            "permissions": "8",  # ADMINISTRATOR
        },
        {
            "id": "103",
            "name": "Manager Server",
            "icon": None,
            "owner": False,
            "permissions": "32",  # MANAGE_GUILD
        },
        {
            "id": "104",
            "name": "Member Server",
            "icon": "icon_104",
            "owner": False,
            "permissions": "1",  # CREATE_INSTANT_INVITE (bukan admin/manage)
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v10/users/@me/guilds":
            assert request.headers["authorization"] == "Bearer tok_guilds"
            return httpx.Response(200, json=discord_guilds)
        return httpx.Response(404)

    settings = make_settings()
    app = create_app(settings=settings, services=api_services)
    app.state.http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async with client_for(app, cookies={settings.session_cookie_name: session.id}) as client:
        response = await client.get(f"{API_PREFIX}/servers")

    assert response.status_code == 200
    data = response.json()

    # Hanya 101, 102, 103 yang muncul (104 tidak punya izin kelola)
    assert len(data) == 3
    server_map = {s["id"]: s for s in data}

    assert "101" in server_map
    assert server_map["101"]["name"] == "Owner Server"
    assert server_map["101"]["icon"] == "icon_101"
    assert server_map["101"]["owner"] is True
    assert server_map["101"]["bot_active"] is True

    assert "102" in server_map
    assert server_map["102"]["name"] == "Admin Server"
    assert server_map["102"]["owner"] is False
    assert server_map["102"]["bot_active"] is False  # Bot nonaktif di DB

    assert "103" in server_map
    assert server_map["103"]["name"] == "Manager Server"
    assert server_map["103"]["owner"] is False
    assert server_map["103"]["bot_active"] is False  # Bot belum join server ini


async def test_servers_caching_avoids_repeated_discord_calls(
    api_services: Services,
) -> None:
    user_id = 999222
    await api_services.onboarding.ensure_user(UserInfo(id=user_id, username="cache_user"))
    session = await api_services.auth.create_session(
        user_id=user_id,
        access_token="tok_cache",
        ttl_s=3600,
    )

    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        if request.url.path == "/api/v10/users/@me/guilds":
            call_count += 1
            return httpx.Response(
                200,
                json=[{"id": "201", "name": "Cached Server", "owner": True, "permissions": "0"}],
            )
        return httpx.Response(404)

    settings = make_settings(guild_cache_ttl_s=60)
    app = create_app(settings=settings, services=api_services)
    app.state.http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async with client_for(app, cookies={settings.session_cookie_name: session.id}) as client:
        # Panggilan pertama: fetch ke Discord
        res1 = await client.get(f"{API_PREFIX}/servers")
        assert res1.status_code == 200
        assert call_count == 1

        # Panggilan kedua: harus menggunakan cache dari sesi
        res2 = await client.get(f"{API_PREFIX}/servers")
        assert res2.status_code == 200
        assert call_count == 1  # Tidak bertambah!


# ---------- GET /servers/{server_id} ----------


async def test_server_detail_success(api_services: Services) -> None:
    user_id = 999333
    server_id = 301
    await api_services.onboarding.ensure_user(UserInfo(id=user_id, username="detail_user"))
    await api_services.onboarding.register_guild(
        GuildInfo(id=server_id, name="Active Guild", owner_id=user_id)
    )
    session = await api_services.auth.create_session(
        user_id=user_id,
        access_token="tok_detail",
        ttl_s=3600,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v10/users/@me/guilds":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": str(server_id),
                        "name": "Active Guild",
                        "icon": "icon_301",
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
        response = await client.get(f"{API_PREFIX}/servers/{server_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(server_id)
    assert data["name"] == "Active Guild"
    assert data["icon"] == "icon_301"
    assert data["owner"] is True
    assert data["bot_active"] is True


async def test_server_detail_unmanageable_returns_403(api_services: Services) -> None:
    user_id = 999444
    server_id = 401
    await api_services.onboarding.ensure_user(UserInfo(id=user_id, username="member_only"))
    await api_services.onboarding.register_guild(
        GuildInfo(id=server_id, name="No Perms Guild", owner_id=123)
    )
    session = await api_services.auth.create_session(
        user_id=user_id,
        access_token="tok_no_perms",
        ttl_s=3600,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v10/users/@me/guilds":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": str(server_id),
                        "name": "No Perms Guild",
                        "icon": None,
                        "owner": False,
                        "permissions": "0",  # Tidak ada izin
                    }
                ],
            )
        return httpx.Response(404)

    settings = make_settings()
    app = create_app(settings=settings, services=api_services)
    app.state.http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async with client_for(app, cookies={settings.session_cookie_name: session.id}) as client:
        response = await client.get(f"{API_PREFIX}/servers/{server_id}")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_server_detail_not_in_user_guilds_returns_403(api_services: Services) -> None:
    user_id = 999555
    server_id = 501
    await api_services.onboarding.ensure_user(UserInfo(id=user_id, username="foreign_user"))
    await api_services.onboarding.register_guild(
        GuildInfo(id=server_id, name="Other Guild", owner_id=111)
    )
    session = await api_services.auth.create_session(
        user_id=user_id,
        access_token="tok_foreign",
        ttl_s=3600,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v10/users/@me/guilds":
            # User sama sekali bukan member di server 501
            return httpx.Response(200, json=[])
        return httpx.Response(404)

    settings = make_settings()
    app = create_app(settings=settings, services=api_services)
    app.state.http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async with client_for(app, cookies={settings.session_cookie_name: session.id}) as client:
        response = await client.get(f"{API_PREFIX}/servers/{server_id}")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_server_detail_inactive_bot_returns_404(api_services: Services) -> None:
    user_id = 999666
    server_id = 601
    await api_services.onboarding.ensure_user(UserInfo(id=user_id, username="inactive_owner"))
    await api_services.onboarding.register_guild(
        GuildInfo(id=server_id, name="Inactive Guild", owner_id=user_id)
    )
    await api_services.onboarding.deactivate_guild(server_id)

    session = await api_services.auth.create_session(
        user_id=user_id,
        access_token="tok_inactive",
        ttl_s=3600,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v10/users/@me/guilds":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": str(server_id),
                        "name": "Inactive Guild",
                        "icon": None,
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
        response = await client.get(f"{API_PREFIX}/servers/{server_id}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_servers_discord_token_expired_returns_401(api_services: Services) -> None:
    user_id = 999777
    await api_services.onboarding.ensure_user(UserInfo(id=user_id, username="expired_tok_user"))
    session = await api_services.auth.create_session(
        user_id=user_id,
        access_token="bad_discord_tok",
        ttl_s=3600,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v10/users/@me/guilds":
            return httpx.Response(401, json={"message": "401: Unauthorized"})
        return httpx.Response(404)

    settings = make_settings()
    app = create_app(settings=settings, services=api_services)
    app.state.http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async with client_for(app, cookies={settings.session_cookie_name: session.id}) as client:
        response = await client.get(f"{API_PREFIX}/servers")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_servers_discord_rate_limited_uses_cache(api_services: Services) -> None:
    user_id = 999888
    await api_services.onboarding.ensure_user(UserInfo(id=user_id, username="ratelimit_user"))
    session = await api_services.auth.create_session(
        user_id=user_id,
        access_token="rl_tok",
        ttl_s=3600,
    )
    # Pre-populate session cache
    cached = [{"id": "801", "name": "Cached Server", "owner": True, "permissions": "0"}]
    await api_services.auth.update_cached_guilds(session.id, cached)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v10/users/@me/guilds":
            return httpx.Response(429, json={"message": "You are being rate limited."})
        return httpx.Response(404)

    # Set cache TTL ke 0 agar memicu fetch baru ke Discord
    settings = make_settings(guild_cache_ttl_s=0)
    app = create_app(settings=settings, services=api_services)
    app.state.http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async with client_for(app, cookies={settings.session_cookie_name: session.id}) as client:
        response = await client.get(f"{API_PREFIX}/servers")

    # Harus fallback ke cached_guilds dengan sukses (200)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == "801"


# ---------- GET & PUT /servers/{server_id}/settings ----------


async def test_get_server_settings_success(api_services: Services) -> None:
    user_id = 111000
    server_id = 701
    await api_services.onboarding.ensure_user(UserInfo(id=user_id, username="settings_owner"))
    await api_services.onboarding.register_guild(
        GuildInfo(id=server_id, name="Settings Server", owner_id=user_id)
    )
    session = await api_services.auth.create_session(
        user_id=user_id,
        access_token="tok_settings",
        ttl_s=3600,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v10/users/@me/guilds":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": str(server_id),
                        "name": "Settings Server",
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
        response = await client.get(f"{API_PREFIX}/servers/{server_id}/settings")

    assert response.status_code == 200
    data = response.json()
    assert data["server_id"] == str(server_id)
    assert data["prefix"] == "!"
    assert data["log_channel_id"] is None
    assert data["welcome_channel_id"] is None
    assert data["features"]["economy"] is True
    assert data["features"]["ai"] is False


async def test_update_server_settings_prefix_and_channels(api_services: Services) -> None:
    user_id = 111001
    server_id = 702
    await api_services.onboarding.ensure_user(UserInfo(id=user_id, username="update_user"))
    await api_services.onboarding.register_guild(
        GuildInfo(id=server_id, name="Update Server", owner_id=user_id)
    )
    session = await api_services.auth.create_session(
        user_id=user_id,
        access_token="tok_update",
        ttl_s=3600,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v10/users/@me/guilds":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": str(server_id),
                        "name": "Update Server",
                        "owner": True,
                        "permissions": "0",
                    }
                ],
            )
        return httpx.Response(404)

    settings = make_settings()
    app = create_app(settings=settings, services=api_services)
    app.state.http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    payload = {
        "prefix": "?",
        "log_channel_id": "1122334455",
        "welcome_channel_id": "9988776655",
        "ai_persona": "Asisten ramah",
    }
    async with client_for(app, cookies={settings.session_cookie_name: session.id}) as client:
        response = await client.put(f"{API_PREFIX}/servers/{server_id}/settings", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["prefix"] == "?"
    assert data["log_channel_id"] == "1122334455"
    assert data["welcome_channel_id"] == "9988776655"
    assert data["ai_persona"] == "Asisten ramah"


async def test_update_server_settings_features(api_services: Services) -> None:
    user_id = 111002
    server_id = 703
    await api_services.onboarding.ensure_user(UserInfo(id=user_id, username="feat_user"))
    await api_services.onboarding.register_guild(
        GuildInfo(id=server_id, name="Feat Server", owner_id=user_id)
    )
    session = await api_services.auth.create_session(
        user_id=user_id,
        access_token="tok_feat",
        ttl_s=3600,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v10/users/@me/guilds":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": str(server_id),
                        "name": "Feat Server",
                        "owner": True,
                        "permissions": "0",
                    }
                ],
            )
        return httpx.Response(404)

    settings = make_settings()
    app = create_app(settings=settings, services=api_services)
    app.state.http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    payload = {
        "features": {
            "ai": True,
            "economy": False,
        }
    }
    async with client_for(app, cookies={settings.session_cookie_name: session.id}) as client:
        response = await client.put(f"{API_PREFIX}/servers/{server_id}/settings", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["features"]["ai"] is True
    assert data["features"]["economy"] is False
    assert data["features"]["fun"] is True  # fitur lain tetap utuh


async def test_update_server_settings_invalid_prefix(api_services: Services) -> None:
    user_id = 111003
    server_id = 704
    await api_services.onboarding.ensure_user(UserInfo(id=user_id, username="bad_prefix_user"))
    await api_services.onboarding.register_guild(
        GuildInfo(id=server_id, name="Bad Prefix Server", owner_id=user_id)
    )
    session = await api_services.auth.create_session(
        user_id=user_id,
        access_token="tok_bad_prefix",
        ttl_s=3600,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v10/users/@me/guilds":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": str(server_id),
                        "name": "Bad Prefix Server",
                        "owner": True,
                        "permissions": "0",
                    }
                ],
            )
        return httpx.Response(404)

    settings = make_settings()
    app = create_app(settings=settings, services=api_services)
    app.state.http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    # Prefix lebih dari 5 karakter
    async with client_for(app, cookies={settings.session_cookie_name: session.id}) as client:
        response = await client.put(
            f"{API_PREFIX}/servers/{server_id}/settings", json={"prefix": "terlalu_panjang"}
        )

    assert response.status_code in (400, 422)


async def test_update_server_settings_invalid_feature(api_services: Services) -> None:
    user_id = 111004
    server_id = 705
    await api_services.onboarding.ensure_user(UserInfo(id=user_id, username="bad_feat_user"))
    await api_services.onboarding.register_guild(
        GuildInfo(id=server_id, name="Bad Feat Server", owner_id=user_id)
    )
    session = await api_services.auth.create_session(
        user_id=user_id,
        access_token="tok_bad_feat",
        ttl_s=3600,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v10/users/@me/guilds":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": str(server_id),
                        "name": "Bad Feat Server",
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
        response = await client.put(
            f"{API_PREFIX}/servers/{server_id}/settings",
            json={"features": {"crypto_mining": True}},
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_failed"


async def test_update_server_settings_clear_channel(api_services: Services) -> None:
    user_id = 111005
    server_id = 706
    await api_services.onboarding.ensure_user(UserInfo(id=user_id, username="clear_ch_user"))
    await api_services.onboarding.register_guild(
        GuildInfo(id=server_id, name="Clear Ch Server", owner_id=user_id)
    )
    # Set log_channel_id awal
    from akizacore.schemas.settings import SettingsUpdate

    await api_services.settings.update(server_id, SettingsUpdate(log_channel_id=99999))

    session = await api_services.auth.create_session(
        user_id=user_id,
        access_token="tok_clear",
        ttl_s=3600,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v10/users/@me/guilds":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": str(server_id),
                        "name": "Clear Ch Server",
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
        response = await client.put(
            f"{API_PREFIX}/servers/{server_id}/settings",
            json={"log_channel_id": None},
        )

    assert response.status_code == 200
    assert response.json()["log_channel_id"] is None


# ---------- GET /servers/{server_id}/stats ----------


async def test_get_server_stats(api_services: Services) -> None:
    user_id = 222001
    server_id = 801
    await api_services.onboarding.ensure_user(UserInfo(id=user_id, username="stats_admin"))
    await api_services.onboarding.register_guild(
        GuildInfo(id=server_id, name="Stats Guild", owner_id=user_id)
    )

    # Seed data
    # 1. Economy account & transaction
    await api_services.economy.credit(server_id, user_id, 500, kind="daily")

    # 2. Moderation warning & log
    await api_services.moderation.warn(
        server_id=server_id, user_id=user_id, mod_id=user_id, reason="Spamming test"
    )

    session = await api_services.auth.create_session(
        user_id=user_id,
        access_token="tok_stats",
        ttl_s=3600,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v10/users/@me/guilds":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": str(server_id),
                        "name": "Stats Guild",
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
        response = await client.get(f"{API_PREFIX}/servers/{server_id}/stats")

    assert response.status_code == 200
    data = response.json()
    assert data["member_count"] == 1
    assert data["economy_accounts"] == 1
    assert data["coins_in_circulation"] == 600  # 100 starter + 500 credit
    assert data["economy_transactions_today"] >= 1
    assert data["active_warnings"] == 1
    assert data["mod_actions_today"] >= 1


# ---------- GET /servers/{server_id}/economy/leaderboard ----------


async def test_get_server_leaderboard(api_services: Services) -> None:
    admin_id = 222002
    server_id = 802
    await api_services.onboarding.ensure_user(UserInfo(id=admin_id, username="leader_admin"))
    await api_services.onboarding.register_guild(
        GuildInfo(id=server_id, name="Leaderboard Guild", owner_id=admin_id)
    )

    # Seed 3 users
    u1, u2, u3 = 222011, 222012, 222013
    await api_services.onboarding.ensure_user(UserInfo(id=u1, username="alice"))
    await api_services.onboarding.ensure_user(UserInfo(id=u2, username="bob"))
    await api_services.onboarding.ensure_user(UserInfo(id=u3, username="charlie"))

    await api_services.economy.credit(server_id, u1, 100, kind="daily")
    await api_services.economy.credit(server_id, u2, 300, kind="daily")
    await api_services.economy.credit(server_id, u3, 200, kind="daily")

    session = await api_services.auth.create_session(
        user_id=admin_id,
        access_token="tok_leader",
        ttl_s=3600,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v10/users/@me/guilds":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": str(server_id),
                        "name": "Leaderboard Guild",
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
        # Page 1, limit 2
        r1 = await client.get(
            f"{API_PREFIX}/servers/{server_id}/economy/leaderboard?page=1&limit=2&sort=balance"
        )
        assert r1.status_code == 200
        d1 = r1.json()
        assert d1["total"] == 3
        assert d1["pages"] == 2
        assert d1["page"] == 1
        assert d1["limit"] == 2
        assert len(d1["items"]) == 2
        assert d1["items"][0]["username"] == "bob"
        assert d1["items"][0]["balance"] == 400
        assert d1["items"][0]["rank"] == 1
        assert d1["items"][1]["username"] == "charlie"
        assert d1["items"][1]["balance"] == 300
        assert d1["items"][1]["rank"] == 2

        # Page 2
        r2 = await client.get(
            f"{API_PREFIX}/servers/{server_id}/economy/leaderboard?page=2&limit=2&sort=balance"
        )
        assert r2.status_code == 200
        d2 = r2.json()
        assert len(d2["items"]) == 1
        assert d2["items"][0]["username"] == "alice"
        assert d2["items"][0]["balance"] == 200
        assert d2["items"][0]["rank"] == 3

        # Invalid sort -> 422
        r3 = await client.get(f"{API_PREFIX}/servers/{server_id}/economy/leaderboard?sort=invalid")
        assert r3.status_code == 422


# ---------- GET /servers/{server_id}/moderation/logs ----------


async def test_get_server_mod_logs(api_services: Services) -> None:
    admin_id = 222003
    server_id = 803
    await api_services.onboarding.ensure_user(UserInfo(id=admin_id, username="mod_admin"))
    await api_services.onboarding.register_guild(
        GuildInfo(id=server_id, name="ModLog Guild", owner_id=admin_id)
    )

    target_id = 222031
    await api_services.onboarding.ensure_user(UserInfo(id=target_id, username="troublemaker"))

    await api_services.moderation.log_action(
        server_id=server_id,
        target_id=target_id,
        mod_id=admin_id,
        action="kick",
        reason="Breaking rule 1",
    )
    await api_services.moderation.log_action(
        server_id=server_id,
        target_id=target_id,
        mod_id=None,
        action="automod_delete",
        reason="Phishing link",
    )

    session = await api_services.auth.create_session(
        user_id=admin_id,
        access_token="tok_modlog",
        ttl_s=3600,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v10/users/@me/guilds":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": str(server_id),
                        "name": "ModLog Guild",
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
        response = await client.get(f"{API_PREFIX}/servers/{server_id}/moderation/logs")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2
    # Check system action (mod_id is None)
    sys_log = next(i for i in data["items"] if i["action"] == "automod_delete")
    assert sys_log["moderator_name"] == "Sistem"
    assert sys_log["target_name"] == "troublemaker"
    assert sys_log["target_id"] == str(target_id)

    # Check manual action
    mod_log = next(i for i in data["items"] if i["action"] == "kick")
    assert mod_log["moderator_name"] == "mod_admin"
    assert mod_log["moderator_id"] == str(admin_id)


# ---------- GET /servers/{server_id}/moderation/warnings ----------


async def test_get_server_warnings(api_services: Services) -> None:
    admin_id = 222004
    server_id = 804
    await api_services.onboarding.ensure_user(UserInfo(id=admin_id, username="warn_admin"))
    await api_services.onboarding.register_guild(
        GuildInfo(id=server_id, name="Warn Guild", owner_id=admin_id)
    )

    u1 = 222041
    u2 = 222042
    await api_services.onboarding.ensure_user(UserInfo(id=u1, username="bad_user1"))
    await api_services.onboarding.ensure_user(UserInfo(id=u2, username="bad_user2"))

    # u1 has 2 warnings, 1 cleared
    await api_services.moderation.warn(
        server_id=server_id, user_id=u1, mod_id=admin_id, reason="Warn 1"
    )
    await api_services.moderation.warn(
        server_id=server_id, user_id=u1, mod_id=admin_id, reason="Warn 2"
    )
    # Clear warnings for u1
    await api_services.moderation.clear_warnings(server_id=server_id, user_id=u1, mod_id=admin_id)
    # Add a new active warning for u1
    await api_services.moderation.warn(
        server_id=server_id, user_id=u1, mod_id=admin_id, reason="Warn 3 (active)"
    )

    # u2 has 1 active warning
    await api_services.moderation.warn(
        server_id=server_id, user_id=u2, mod_id=admin_id, reason="Warn for u2"
    )

    session = await api_services.auth.create_session(
        user_id=admin_id,
        access_token="tok_warnings",
        ttl_s=3600,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v10/users/@me/guilds":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": str(server_id),
                        "name": "Warn Guild",
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
        # 1. All active warnings
        res_all = await client.get(f"{API_PREFIX}/servers/{server_id}/moderation/warnings")
        assert res_all.status_code == 200
        data_all = res_all.json()
        assert data_all["total"] == 2
        assert len(data_all["items"]) == 2

        # 2. Filter by user_id
        res_u1 = await client.get(
            f"{API_PREFIX}/servers/{server_id}/moderation/warnings?user_id={u1}"
        )
        assert res_u1.status_code == 200
        data_u1 = res_u1.json()
        assert data_u1["total"] == 1
        assert data_u1["items"][0]["username"] == "bad_user1"
        assert data_u1["items"][0]["reason"] == "Warn 3 (active)"

        # 3. Alias /warnings endpoint
        res_alias = await client.get(f"{API_PREFIX}/servers/{server_id}/warnings")
        assert res_alias.status_code == 200
        assert res_alias.json()["total"] == 2
