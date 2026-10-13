import secrets
import urllib.parse
from typing import Any

import httpx
import structlog
from fastapi import APIRouter, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from akizacore.api.deps import CurrentUserDep, HttpClientDep, ServicesDep, SettingsDep
from akizacore.core.exceptions import ValidationFailed
from akizacore.schemas.discord import UserInfo

log = structlog.get_logger()
router = APIRouter(prefix="/auth", tags=["auth"])

OAUTH_STATE_COOKIE = "akiza_oauth_state"
DISCORD_API_BASE = "https://discord.com/api/v10"


class CurrentUserResponse(BaseModel):
    id: str
    username: str
    discriminator: str = "0"
    avatar: str | None = None
    global_name: str | None = None


@router.get("/discord/login", summary="Redirect ke otorisasi Discord OAuth2")
async def discord_login(settings: SettingsDep) -> RedirectResponse:
    if not settings.discord_client_id:
        raise ValidationFailed("DISCORD_CLIENT_ID belum dikonfigurasi.")
    state = secrets.token_urlsafe(32)
    params = {
        "client_id": settings.discord_client_id,
        "response_type": "code",
        "redirect_uri": settings.discord_oauth_redirect_uri,
        "scope": "identify guilds",
        "state": state,
        "prompt": "consent",
    }
    url = f"https://discord.com/oauth2/authorize?{urllib.parse.urlencode(params)}"
    response = RedirectResponse(url=url, status_code=307)
    response.set_cookie(
        key=OAUTH_STATE_COOKIE,
        value=state,
        httponly=True,
        samesite="lax",
        secure=settings.environment == "prod",
        max_age=300,
        path="/",
    )
    return response


@router.get("/discord/callback", summary="Callback OAuth2 Discord")
async def discord_callback(
    request: Request,
    settings: SettingsDep,
    services: ServicesDep,
    http_client: HttpClientDep,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
) -> RedirectResponse:
    # 1. Bila Discord mengirim error (mis. user membatalkan di halaman login)
    if error:
        redirect_url = f"{settings.dashboard_url}/login?error={urllib.parse.quote(error)}"
        response = RedirectResponse(url=redirect_url, status_code=307)
        response.delete_cookie(
            key=OAUTH_STATE_COOKIE,
            path="/",
            httponly=True,
            samesite="lax",
            secure=settings.environment == "prod",
        )
        return response

    # 2. Validasi state CSRF
    expected_state = request.cookies.get(OAUTH_STATE_COOKIE)
    if not expected_state or not state or expected_state != state:
        raise ValidationFailed("State OAuth tidak valid atau sesi sudah kedaluwarsa.")

    # 3. Validasi authorization code
    if not code:
        raise ValidationFailed("Authorization code tidak ditemukan.")

    # 4. Tukar code dengan token Discord
    async def _exchange_and_fetch(
        client: httpx.AsyncClient,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        token_res = await client.post(
            f"{DISCORD_API_BASE}/oauth2/token",
            data={
                "client_id": settings.discord_client_id,
                "client_secret": settings.discord_client_secret.get_secret_value(),
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.discord_oauth_redirect_uri,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if token_res.status_code != 200:
            log.warning(
                "discord_token_exchange_failed",
                status=token_res.status_code,
                body=token_res.text,
            )
            raise ValidationFailed("Gagal menukar code Discord.")
        tokens: dict[str, Any] = token_res.json()

        user_res = await client.get(
            f"{DISCORD_API_BASE}/users/@me",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )
        if user_res.status_code != 200:
            log.warning(
                "discord_user_fetch_failed",
                status=user_res.status_code,
                body=user_res.text,
            )
            raise ValidationFailed("Gagal mengambil profil Discord.")
        user_info: dict[str, Any] = user_res.json()
        return tokens, user_info

    if http_client is not None:
        token_data, user_data = await _exchange_and_fetch(http_client)
    else:
        async with httpx.AsyncClient() as client:
            token_data, user_data = await _exchange_and_fetch(client)

    user_id = int(user_data["id"])
    username = str(user_data.get("username", ""))
    avatar = user_data.get("avatar")
    global_name = user_data.get("global_name")

    # 5. Pastikan user terdaftar di database
    await services.onboarding.ensure_user(
        UserInfo(
            id=user_id,
            username=username,
            avatar=avatar,
            global_name=global_name,
        )
    )

    # 6. Buat sesi di database
    session = await services.auth.create_session(
        user_id=user_id,
        access_token=token_data["access_token"],
        refresh_token=token_data.get("refresh_token"),
        scope=token_data.get("scope", "identify guilds"),
        ttl_s=settings.session_ttl_s,
    )

    # 7. Set cookie sesi dan redirect ke callback dashboard
    redirect_url = f"{settings.dashboard_url}/callback"
    response = RedirectResponse(url=redirect_url, status_code=307)
    response.set_cookie(
        key=settings.session_cookie_name,
        value=session.id,
        httponly=True,
        samesite="lax",
        secure=settings.environment == "prod",
        max_age=settings.session_ttl_s,
        path="/",
    )
    response.delete_cookie(
        key=OAUTH_STATE_COOKIE,
        path="/",
        httponly=True,
        samesite="lax",
        secure=settings.environment == "prod",
    )
    return response


@router.post("/logout", summary="Logout dan cabut sesi", status_code=204)
async def logout(
    request: Request,
    settings: SettingsDep,
    services: ServicesDep,
) -> Response:
    session_id = request.cookies.get(settings.session_cookie_name)
    if session_id:
        await services.auth.revoke_session(session_id)

    response = Response(status_code=204)
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        httponly=True,
        samesite="lax",
        secure=settings.environment == "prod",
    )
    return response


@router.get("/me", summary="Profil user yang sedang login", response_model=CurrentUserResponse)
async def me(user: CurrentUserDep) -> CurrentUserResponse:
    return CurrentUserResponse(
        id=str(user.id),
        username=user.username,
        discriminator="0",
        avatar=user.avatar,
        global_name=user.global_name,
    )
