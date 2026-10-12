import asyncio
import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from akizacore.ai.config import AIConfig
from akizacore.ai.context import build_messages
from akizacore.ai.providers.base import ChatMessage, LLMProvider
from akizacore.core.exceptions import PermissionDenied, QuotaExceeded, ValidationFailed
from akizacore.database.repositories import (
    AIUsageRepository,
    ConversationRepository,
    UserRepository,
)
from akizacore.database.session import session_scope
from akizacore.schemas.discord import UserInfo
from akizacore.services.economy import EconomyService
from akizacore.services.settings import SettingsService

log = structlog.get_logger()


@dataclass(frozen=True)
class AskRequest:
    server_id: int
    server_name: str
    channel_id: int
    user: UserInfo
    prompt: str


@dataclass(frozen=True)
class AskResult:
    text: str
    model: str
    coins_charged: int
    balance_after: int | None


class AIOrchestrator:
    """Alur: validasi -> fitur/opt-out -> cooldown -> kuota -> potong koin -> LLM -> simpan.

    Bila langkah setelah pemotongan koin gagal, koin dikembalikan otomatis.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        llm: LLMProvider,
        economy: EconomyService,
        settings: SettingsService,
        config: AIConfig,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._sf = session_factory
        self._llm = llm
        self._economy = economy
        self._settings = settings
        self._cfg = config
        self._clock = clock
        self._last_call: dict[int, float] = {}

    async def ask(self, req: AskRequest) -> AskResult:
        cfg = self._cfg
        prompt = req.prompt.strip()
        if not prompt:
            raise ValidationFailed("Pertanyaan tidak boleh kosong.")
        if len(prompt) > cfg.max_input_chars:
            raise ValidationFailed(
                f"Pertanyaan terlalu panjang (maksimal {cfg.max_input_chars} karakter)."
            )

        server_settings = await self._settings.get(req.server_id)
        if not server_settings.features.get("ai"):
            raise PermissionDenied(
                "Modul AI belum aktif di server ini. Admin bisa menyalakannya dengan /setup feature."
            )

        language, opted_out = await self._load_profile(req.user.id)
        if opted_out:
            raise PermissionDenied("Kamu menonaktifkan fitur AI untuk akunmu.")

        self._check_cooldown(req.user.id)
        await self._check_quota(req.user.id)

        charged = 0
        balance: int | None = None
        if cfg.cost_coins > 0:
            balance = await self._economy.charge(
                req.server_id,
                req.user.id,
                cfg.cost_coins,
                kind="ai_ask",
                meta={"channel_id": req.channel_id},
            )
            charged = cfg.cost_coins

        try:
            return await self._respond(
                req, prompt, server_settings.ai_persona, language, charged, balance
            )
        except (Exception, asyncio.CancelledError):
            if charged:
                await self._refund(req, charged)
            raise

    async def forget(self, server_id: int, user_id: int) -> int:
        async with session_scope(self._sf) as session:
            return await ConversationRepository(session).delete_for_user(server_id, user_id)

    async def _respond(
        self,
        req: AskRequest,
        prompt: str,
        persona: str | None,
        language: str,
        charged: int,
        balance: int | None,
    ) -> AskResult:
        cfg = self._cfg
        async with session_scope(self._sf) as session:
            repo = ConversationRepository(session)
            conversation_id = await repo.get_or_create(req.server_id, req.user.id, req.channel_id)
            rows = await repo.recent_messages(conversation_id, cfg.history_messages)
        history = [
            ChatMessage("assistant" if row.role == "assistant" else "user", row.content)
            for row in rows
        ]

        messages = build_messages(
            persona_override=persona,
            server_name=req.server_name,
            user_name=req.user.username,
            language=language,
            history=history,
            prompt=prompt,
            history_max_chars=cfg.history_max_chars,
        )
        response = await self._llm.chat(messages, max_tokens=cfg.max_output_tokens)

        async with session_scope(self._sf) as session:
            await ConversationRepository(session).add_messages(
                conversation_id,
                [
                    ("user", prompt, response.prompt_tokens),
                    ("assistant", response.content, response.completion_tokens),
                ],
            )
            await AIUsageRepository(session).add(
                server_id=req.server_id,
                user_id=req.user.id,
                model=response.model,
                prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
                coins=charged,
            )
        return AskResult(
            text=response.content,
            model=response.model,
            coins_charged=charged,
            balance_after=balance,
        )

    async def _refund(self, req: AskRequest, amount: int) -> None:
        try:
            await self._economy.credit(
                req.server_id, req.user.id, amount, kind="ai_refund", meta={"reason": "ai_failed"}
            )
        except Exception:
            log.error("refund_failed", server_id=req.server_id, user_id=req.user.id, amount=amount)

    async def _load_profile(self, user_id: int) -> tuple[str, bool]:
        async with session_scope(self._sf) as session:
            profile = await UserRepository(session).get_profile(user_id)
            if profile is None:
                return "id", False
            return profile.language, profile.ai_opt_out

    def _check_cooldown(self, user_id: int) -> None:
        now = self._clock()
        last = self._last_call.get(user_id)
        if last is not None and now - last < self._cfg.cooldown_s:
            remaining = math.ceil(self._cfg.cooldown_s - (now - last))
            raise QuotaExceeded(f"Tunggu {remaining} detik lagi sebelum bertanya.")
        self._last_call[user_id] = now

    def _day_start(self) -> datetime:
        tz = timezone(timedelta(hours=self._cfg.utc_offset_hours))
        return datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)

    async def _check_quota(self, user_id: int) -> None:
        since = self._day_start()
        async with session_scope(self._sf) as session:
            repo = AIUsageRepository(session)
            if await repo.count_since(since) >= self._cfg.daily_global_limit:
                raise QuotaExceeded("Kuota AI harian bot sudah habis. Coba lagi besok.")
            if await repo.count_since(since, user_id=user_id) >= self._cfg.daily_user_limit:
                raise QuotaExceeded(
                    f"Batas {self._cfg.daily_user_limit} pertanyaan AI per hari sudah tercapai."
                )
