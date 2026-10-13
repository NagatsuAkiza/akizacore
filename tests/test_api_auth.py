import urllib.parse
from typing import Any

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from akizacore.api.app import API_PREFIX, create_app
from akizacore.config import ApiSettings
from akizacore.services.container import Services

CLIENT_ID = "123456789012345678"
CLIENT_SECRET = "super_secret_discord_client_secret"
REDIRECT_URI = "http://localhost:8000/api/v1/auth/discord/callback"
DASHBOARD_URL = "http://localhost:5173"


def make_settings(**kwargs: Any) -> ApiSettings:
    defaults: dict[str, Any] = {
        "discord_client_id": CLIENT_ID,
        "discord_client_secret": SecretStr(CLIENT_SECRET),
        "discord_oauth_redirect_uri": REDIRECT_URI,
        "dashboard_url": DASHBOARD_URL,
    }
    defaults.update(kwargs)
    return ApiSettings(**defaults)


def client_for(app: Any, cookies: dict[str, str] | None = None) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://test", cookies=cookies)


@pytest.fixture
def auth_services(session_factory: async_sessionmaker[AsyncSession]) -> Services:
    return Services.build(session_factory)


# ---------- GET /auth/discord/login ----------


async def test_discord_login_redirects_and_sets_state_cookie(
    auth_services: Services,
) -> None:
    settings = make_settings()
    app = create_app(settings=settings, services=auth_services)

    async with client_for(app) as client:
        response = await client.get(f"{API_PREFIX}/auth/discord/login")

    assert response.status_code == 307
    location = response.headers.get("location", "")
    assert location.startswith("https://discord.com/oauth2/authorize?")

    parsed = urllib.parse.urlparse(location)
    params = urllib.parse.parse_qs(parsed.query)

    assert params["client_id"] == [CLIENT_ID]
    assert params["redirect_uri"] == [REDIRECT_URI]
    assert params["response_type"] == ["code"]
    assert params["scope"] == ["identify guilds"]
    state = params["state"][0]
    assert len(state) >= 16

    # Cek cookie akiza_oauth_state
    set_cookie = response.headers.get("set-cookie", "")
    assert "akiza_oauth_state=" in set_cookie
    assert f"akiza_oauth_state={state}" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie


async def test_discord_login_requires_client_id(auth_services: Services) -> None:
    settings = make_settings(discord_client_id="")
    app = create_app(settings=settings, services=auth_services)

    async with client_for(app) as client:
        response = await client.get(f"{API_PREFIX}/auth/discord/login")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_failed"


# ---------- GET /auth/discord/callback ----------


async def test_discord_callback_with_discord_error_redirects_to_login(
    auth_services: Services,
) -> None:
    settings = make_settings()
    app = create_app(settings=settings, services=auth_services)

    async with client_for(app, cookies={"akiza_oauth_state": "some_state"}) as client:
        response = await client.get(
            f"{API_PREFIX}/auth/discord/callback?error=access_denied&error_description=User+denied",
        )

    assert response.status_code == 307
    location = response.headers.get("location", "")
    assert location == f"{DASHBOARD_URL}/login?error=access_denied"


async def test_discord_callback_fails_with_mismatched_state(
    auth_services: Services,
) -> None:
    settings = make_settings()
    app = create_app(settings=settings, services=auth_services)

    async with client_for(app, cookies={"akiza_oauth_state": "expected_state"}) as client:
        response = await client.get(
            f"{API_PREFIX}/auth/discord/callback?code=good_code&state=wrong_state",
        )

    assert response.status_code == 400
    data = response.json()
    assert data["error"]["code"] == "validation_failed"
    assert "State OAuth" in data["error"]["message"]


async def test_discord_callback_fails_without_state_cookie(
    auth_services: Services,
) -> None:
    settings = make_settings()
    app = create_app(settings=settings, services=auth_services)

    async with client_for(app) as client:
        response = await client.get(
            f"{API_PREFIX}/auth/discord/callback?code=good_code&state=some_state"
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_failed"


async def test_discord_callback_fails_without_code(auth_services: Services) -> None:
    settings = make_settings()
    app = create_app(settings=settings, services=auth_services)

    async with client_for(app, cookies={"akiza_oauth_state": "my_state"}) as client:
        response = await client.get(
            f"{API_PREFIX}/auth/discord/callback?state=my_state",
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_failed"
    assert "Authorization code" in response.json()["error"]["message"]


async def test_discord_callback_invalid_code_with_mock_transport(
    auth_services: Services,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        # Simulasi Discord menolak code
        if request.url.path == "/api/v10/oauth2/token":
            return httpx.Response(400, json={"error": "invalid_grant"})
        return httpx.Response(404)

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = make_settings()
    app = create_app(settings=settings, services=auth_services)
    app.state.http_client = mock_client

    async with client_for(app, cookies={"akiza_oauth_state": "test_state"}) as client:
        response = await client.get(
            f"{API_PREFIX}/auth/discord/callback?code=bad_code&state=test_state",
        )

    assert response.status_code == 400
    data = response.json()
    assert data["error"]["code"] == "validation_failed"
    assert "Gagal menukar code" in data["error"]["message"]


async def test_discord_callback_profile_fetch_failure_with_mock_transport(
    auth_services: Services,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v10/oauth2/token":
            return httpx.Response(
                200,
                json={
                    "access_token": "mock_access_token",
                    "refresh_token": "mock_refresh_token",
                    "scope": "identify guilds",
                },
            )
        if request.url.path == "/api/v10/users/@me":
            return httpx.Response(401, json={"message": "401: Unauthorized"})
        return httpx.Response(404)

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = make_settings()
    app = create_app(settings=settings, services=auth_services)
    app.state.http_client = mock_client

    async with client_for(app, cookies={"akiza_oauth_state": "test_state"}) as client:
        response = await client.get(
            f"{API_PREFIX}/auth/discord/callback?code=valid_code&state=test_state",
        )

    assert response.status_code == 400
    assert "Gagal mengambil profil" in response.json()["error"]["message"]


async def test_discord_callback_success_creates_session_and_cookie(
    auth_services: Services,
) -> None:
    user_discord_id = 998877665544332211
    username = "nagatsu"
    global_name = "Nagatsu Akiza"
    avatar = "abc123avatarhash"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v10/oauth2/token":
            return httpx.Response(
                200,
                json={
                    "access_token": "valid_token_xyz",
                    "refresh_token": "refresh_token_xyz",
                    "scope": "identify guilds",
                },
            )
        if request.url.path == "/api/v10/users/@me":
            assert request.headers["authorization"] == "Bearer valid_token_xyz"
            return httpx.Response(
                200,
                json={
                    "id": str(user_discord_id),
                    "username": username,
                    "global_name": global_name,
                    "avatar": avatar,
                    "discriminator": "0",
                },
            )
        return httpx.Response(404)

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = make_settings()
    app = create_app(settings=settings, services=auth_services)
    app.state.http_client = mock_client

    async with client_for(app, cookies={"akiza_oauth_state": "state_abc"}) as client:
        response = await client.get(
            f"{API_PREFIX}/auth/discord/callback?code=good_code&state=state_abc",
        )

    assert response.status_code == 307
    assert response.headers["location"] == f"{DASHBOARD_URL}/callback"

    # Cek session cookie di header
    set_cookie = response.headers.get("set-cookie", "")
    assert f"{settings.session_cookie_name}=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie

    # Ambil session ID dari cookie
    cookie_str = response.cookies.get(settings.session_cookie_name)
    assert cookie_str is not None

    # Verifikasi sesi ada di database
    session_obj = await auth_services.auth.get_session(cookie_str)
    assert session_obj is not None
    assert session_obj.user_id == user_discord_id
    assert session_obj.access_token == "valid_token_xyz"

    # Verifikasi profil user tersimpan di DB
    user_obj = await auth_services.auth.get_user_by_session(cookie_str)
    assert user_obj is not None
    assert user_obj.id == user_discord_id
    assert user_obj.username == username
    assert user_obj.global_name == global_name
    assert user_obj.avatar == avatar


# ---------- GET /auth/me ----------


async def test_auth_me_unauthenticated_returns_401(auth_services: Services) -> None:
    settings = make_settings()
    app = create_app(settings=settings, services=auth_services)

    async with client_for(app) as client:
        response = await client.get(f"{API_PREFIX}/auth/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"
    assert response.json()["error"]["message"] == "Kamu belum login."


async def test_auth_me_with_invalid_session_cookie_returns_401(
    auth_services: Services,
) -> None:
    settings = make_settings()
    app = create_app(settings=settings, services=auth_services)

    async with client_for(
        app, cookies={settings.session_cookie_name: "non_existent_session_token"}
    ) as client:
        response = await client.get(f"{API_PREFIX}/auth/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_auth_me_with_expired_session_returns_401(
    auth_services: Services,
) -> None:
    from akizacore.schemas.discord import UserInfo

    user_id = 1122334455
    await auth_services.onboarding.ensure_user(UserInfo(id=user_id, username="test_expired"))
    settings = make_settings()
    # Buat sesi dengan TTL negatif (langsung expired)
    session = await auth_services.auth.create_session(
        user_id=user_id,
        access_token="expired_tok",
        ttl_s=-10,
    )
    app = create_app(settings=settings, services=auth_services)

    async with client_for(app, cookies={settings.session_cookie_name: session.id}) as client:
        response = await client.get(f"{API_PREFIX}/auth/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_auth_me_authenticated_returns_profile(auth_services: Services) -> None:
    from akizacore.schemas.discord import UserInfo

    user_id = 112233445566778899
    await auth_services.onboarding.ensure_user(
        UserInfo(
            id=user_id,
            username="kuroba",
            avatar="avatar_hash_123",
            global_name="Kuroba Kaito",
        )
    )
    session = await auth_services.auth.create_session(
        user_id=user_id,
        access_token="tok_abc",
        ttl_s=3600,
    )

    settings = make_settings()
    app = create_app(settings=settings, services=auth_services)

    async with client_for(app, cookies={settings.session_cookie_name: session.id}) as client:
        response = await client.get(f"{API_PREFIX}/auth/me")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(user_id)
    assert data["username"] == "kuroba"
    assert data["global_name"] == "Kuroba Kaito"
    assert data["avatar"] == "avatar_hash_123"
    assert data["discriminator"] == "0"


# ---------- POST /auth/logout ----------


async def test_logout_revokes_session_and_clears_cookie(
    auth_services: Services,
) -> None:
    from akizacore.schemas.discord import UserInfo

    user_id = 9988112233
    await auth_services.onboarding.ensure_user(
        UserInfo(id=user_id, username="logout_user", global_name="Logout User")
    )
    session = await auth_services.auth.create_session(
        user_id=user_id,
        access_token="tok_logout",
        ttl_s=3600,
    )

    settings = make_settings()
    app = create_app(settings=settings, services=auth_services)

    async with client_for(app, cookies={settings.session_cookie_name: session.id}) as client:
        # Pastikan sebelum logout /auth/me berhasil
        res_before = await client.get(f"{API_PREFIX}/auth/me")
        assert res_before.status_code == 200

        # Lakukan logout
        res_logout = await client.post(f"{API_PREFIX}/auth/logout")
        assert res_logout.status_code == 204

        # Cek cookie dihapus (max-age=0)
        set_cookie = res_logout.headers.get("set-cookie", "")
        assert f"{settings.session_cookie_name}=" in set_cookie
        assert "Max-Age=0" in set_cookie or "expires=" in set_cookie.lower()

        # Cek setelah logout, session tidak bisa dipakai lagi
        res_after = await client.get(f"{API_PREFIX}/auth/me")
        assert res_after.status_code == 401

    # Verifikasi sesi juga terhapus dari database
    sess_db = await auth_services.auth.get_session(session.id)
    assert sess_db is None
