import asyncio
import json
import math
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from akizacore.ai.config import AIConfig
from akizacore.ai.context import ReplyContext, build_messages, build_translate_messages
from akizacore.ai.providers.base import ChatMessage, LLMProvider, ToolSpec
from akizacore.ai.router import match_rule
from akizacore.ai.tools import ModerationGateway, ToolContext, ToolExecutor, ToolRegistry
from akizacore.core.exceptions import (
    PermissionDenied,
    ProviderUnavailable,
    QuotaExceeded,
    ValidationFailed,
)
from akizacore.database.repositories import (
    AIUsageRepository,
    ConversationRepository,
    UserRepository,
)
from akizacore.database.session import session_scope
from akizacore.schemas.discord import UserInfo
from akizacore.services.economy import EconomyService
from akizacore.services.memory import MemoryService
from akizacore.services.settings import SettingsService

log = structlog.get_logger()

MAX_CALLS_PER_ROUND = 4


@dataclass(frozen=True)
class AskRequest:
    server_id: int
    server_name: str
    channel_id: int
    user: UserInfo
    prompt: str
    is_admin: bool = (
        False  # snapshot izin Manage Server dari Discord, dipakai untuk tool khusus admin
    )
    reply_context: ReplyContext | None = None
    moderation: ModerationGateway | None = None


@dataclass(frozen=True)
class TranslateRequest:
    server_id: int
    user: UserInfo
    text: str
    target_language: str


@dataclass(frozen=True)
class AskResult:
    text: str
    model: str
    coins_charged: int
    balance_after: int | None
    tools_used: tuple[str, ...] = ()


@dataclass(frozen=True)
class _Admission:
    language: str
    persona: str | None
    features: dict[str, bool]
    opted_out: bool


@dataclass(frozen=True)
class _Completion:
    text: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    tools_used: tuple[str, ...]


Work = Callable[[int, int | None], Awaitable[AskResult]]


class AIOrchestrator:
    """Alur chat: validasi -> fitur/opt-out -> rule router -> cooldown -> kuota -> potong koin ->
    LLM (dengan tool calling) -> simpan.

    - Rule router (pertanyaan sederhana seperti "saldo saya") dijawab tanpa LLM dan tanpa koin.
    - Tool calling berjalan dalam panggilan LLM yang sama (tanpa klasifikasi terpisah) agar hemat kuota.
    - Bila langkah setelah pemotongan koin gagal, koin dikembalikan otomatis.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        llm: LLMProvider,
        economy: EconomyService,
        settings: SettingsService,
        memory: MemoryService,
        config: AIConfig,
        tools: ToolRegistry | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._sf = session_factory
        self._llm = llm
        self._economy = economy
        self._settings = settings
        self._memory = memory
        self._cfg = config
        self._tools = tools
        self._executor = ToolExecutor(tools) if tools is not None else None
        self._clock = clock
        self._last_call: dict[int, float] = {}

    @property
    def retention_days(self) -> int:
        return self._cfg.retention_days

    # ---------- Use case ----------
    async def ask(self, req: AskRequest) -> AskResult:
        prompt = self._validate_text(req.prompt)
        is_owner = self._is_owner(req.user.id)
        admission = await self._admit(req.server_id, req.user.id)
        ctx = ToolContext(
            server_id=req.server_id,
            user=req.user,
            is_admin=req.is_admin,
            features=admission.features,
            moderation=req.moderation,
        )

        ruled = await self._try_rule(prompt, ctx)
        if ruled is not None:
            return ruled

        if not is_owner:
            self._check_cooldown(req.user.id)
            await self._check_quota(req.server_id, req.user.id, "ask")

        async def work(charged: int, balance: int | None) -> AskResult:
            return await self._chat(req, prompt, admission, ctx, charged, balance)

        return await self._billed(
            req.server_id, req.user.id, "ai_ask", {"channel_id": req.channel_id}, work
        )

    async def translate(self, req: TranslateRequest) -> AskResult:
        text = self._validate_text(req.text)
        target = " ".join(req.target_language.split())[:30]
        if len(target) < 2:
            raise ValidationFailed("Bahasa tujuan tidak valid.")
        await self._admit(req.server_id, req.user.id)
        if not self._is_owner(req.user.id):
            self._check_cooldown(req.user.id)
            await self._check_quota(req.server_id, req.user.id, "translate")

        async def work(charged: int, balance: int | None) -> AskResult:
            started = time.perf_counter()
            response = await self._llm.chat(
                build_translate_messages(text, target), max_tokens=self._cfg.max_output_tokens
            )
            latency_ms = round((time.perf_counter() - started) * 1000)
            if not response.content:
                raise ProviderUnavailable("respons terjemahan kosong", retryable=False)
            async with session_scope(self._sf) as session:
                await AIUsageRepository(session).add(
                    server_id=req.server_id,
                    user_id=req.user.id,
                    model=response.model,
                    prompt_tokens=response.prompt_tokens,
                    completion_tokens=response.completion_tokens,
                    coins=charged,
                    kind="translate",
                    latency_ms=latency_ms,
                )
            return AskResult(
                text=response.content,
                model=response.model,
                coins_charged=charged,
                balance_after=balance,
            )

        return await self._billed(
            req.server_id, req.user.id, "ai_translate", {"target": target}, work
        )

    async def forget(self, server_id: int, user_id: int) -> int:
        async with session_scope(self._sf) as session:
            return await ConversationRepository(session).delete_for_user(server_id, user_id)

    async def purge_expired(self, now: datetime | None = None) -> tuple[int, int]:
        """Hapus riwayat melewati masa retensi. Return (pesan dihapus, percakapan dihapus)."""
        cutoff = (now or datetime.now(UTC)) - timedelta(days=self._cfg.retention_days)
        async with session_scope(self._sf) as session:
            return await ConversationRepository(session).purge_older_than(cutoff)

    # ---------- Tahapan ----------
    def _validate_text(self, text: str) -> str:
        cleaned = text.strip()
        if not cleaned:
            raise ValidationFailed("Teks tidak boleh kosong.")
        if len(cleaned) > self._cfg.max_input_chars:
            raise ValidationFailed(
                f"Teks terlalu panjang (maksimal {self._cfg.max_input_chars} karakter)."
            )
        return cleaned

    async def _admit(self, server_id: int, user_id: int) -> _Admission:
        server_settings = await self._settings.get(server_id)
        is_owner = self._is_owner(user_id)
        if not is_owner and not server_settings.features.get("ai"):
            raise PermissionDenied(
                "Modul AI belum aktif di server ini. Admin bisa menyalakannya dengan /setup feature."
            )
        language, opted_out = await self._load_profile(user_id)
        if opted_out and not is_owner:
            raise PermissionDenied("Kamu menonaktifkan fitur AI untuk akunmu.")
        return _Admission(language, server_settings.ai_persona, server_settings.features, opted_out)

    async def _try_rule(self, prompt: str, ctx: ToolContext) -> AskResult | None:
        if self._tools is None or self._executor is None:
            return None
        match = match_rule(prompt)
        if match is None:
            return None
        tool = self._tools.get(match.tool)
        if tool is None or self._tools.unavailable_reason(tool, ctx) is not None:
            return None  # modul dimatikan / tidak berhak: biarkan LLM yang menanggapi
        started = time.perf_counter()
        text = await self._executor.run_named(match.tool, json.dumps(match.args), ctx)
        await self._record_usage(
            server_id=ctx.server_id,
            user_id=ctx.user.id,
            model=f"rule:{match.tool}",
            kind="rule",
            latency_ms=round((time.perf_counter() - started) * 1000),
            tools=(match.tool,),
        )
        return AskResult(
            text=text,
            model=f"rule:{match.tool}",
            coins_charged=0,
            balance_after=None,
            tools_used=(match.tool,),
        )

    async def _billed(
        self,
        server_id: int,
        user_id: int,
        kind: str,
        meta: dict[str, object],
        work: Work,
    ) -> AskResult:
        charged = 0
        balance: int | None = None
        if self._cfg.cost_coins > 0 and not self._is_owner(user_id):
            balance = await self._economy.charge(
                server_id, user_id, self._cfg.cost_coins, kind=kind, meta=meta
            )
            charged = self._cfg.cost_coins
        started = time.perf_counter()
        try:
            return await work(charged, balance)
        except (Exception, asyncio.CancelledError) as exc:
            if charged:
                await self._refund(server_id, user_id, charged)
            if not isinstance(exc, asyncio.CancelledError):
                await self._record_usage(
                    server_id=server_id,
                    user_id=user_id,
                    model="-",
                    kind=kind.removeprefix("ai_"),
                    status="error",
                    latency_ms=round((time.perf_counter() - started) * 1000),
                    error_code=type(exc).__name__[:60],
                )
            raise

    async def _chat(
        self,
        req: AskRequest,
        prompt: str,
        admission: _Admission,
        ctx: ToolContext,
        charged: int,
        balance: int | None,
    ) -> AskResult:
        cfg = self._cfg
        async with session_scope(self._sf) as session:
            repo = ConversationRepository(session)
            conversation_id = await repo.get_or_create(req.server_id, req.user.id, req.channel_id)
            rows = await repo.recent_messages(conversation_id, cfg.history_messages)
        history = [
            ChatMessage(
                "assistant" if row.role == "assistant" else "user",
                f"[AkizaCore]: {row.content}"
                if row.role == "assistant"
                else f"[{req.user.username}]: {row.content}",
            )
            for row in rows
        ]
        memories = (
            await self._memory.context_for_ai(req.server_id, req.user.id)
            if not admission.opted_out
            else []
        )
        memories = memories[: max(0, cfg.memory_limit)]

        specs = self._tools.specs_for(ctx) if self._tools is not None else []
        messages = build_messages(
            persona_override=admission.persona,
            server_name=req.server_name,
            user_name=req.user.username,
            language=admission.language,
            history=history,
            prompt=prompt,
            history_max_chars=cfg.history_max_chars,
            memories=[memory.content for memory in memories],
            memory_max_chars=cfg.memory_max_chars,
            tools_enabled=bool(specs),
            is_bot_owner=self._is_owner(req.user.id),
            reply_context=req.reply_context,
        )
        started = time.perf_counter()
        completion = await self._complete(messages, specs, ctx)
        latency_ms = round((time.perf_counter() - started) * 1000)

        async with session_scope(self._sf) as session:
            await ConversationRepository(session).add_messages(
                conversation_id,
                [
                    ("user", prompt, completion.prompt_tokens),
                    ("assistant", completion.text, completion.completion_tokens),
                ],
            )
            await AIUsageRepository(session).add(
                server_id=req.server_id,
                user_id=req.user.id,
                model=completion.model,
                prompt_tokens=completion.prompt_tokens,
                completion_tokens=completion.completion_tokens,
                coins=charged,
                kind="ask",
                latency_ms=latency_ms,
                tools=completion.tools_used,
            )
        return AskResult(
            text=completion.text,
            model=completion.model,
            coins_charged=charged,
            balance_after=balance,
            tools_used=completion.tools_used,
        )

    async def _complete(
        self, messages: list[ChatMessage], specs: list[ToolSpec], ctx: ToolContext
    ) -> _Completion:
        """Putaran LLM: bila model meminta tool, jalankan lalu kembalikan hasilnya (maks N putaran).
        Putaran terakhir tanpa tool agar model wajib menjawab dengan teks."""
        cfg = self._cfg
        rounds = cfg.max_tool_rounds if specs and self._executor is not None else 0
        conversation = list(messages)
        prompt_tokens = completion_tokens = 0
        used: list[str] = []

        for attempt in range(rounds + 1):
            offer = specs if attempt < rounds else None
            response = await self._llm.chat(
                conversation, tools=offer, max_tokens=cfg.max_output_tokens
            )
            prompt_tokens += response.prompt_tokens
            completion_tokens += response.completion_tokens

            if not response.tool_calls or offer is None:
                if not response.content:
                    raise ProviderUnavailable("model tidak memberi jawaban", retryable=False)
                return _Completion(
                    response.content, response.model, prompt_tokens, completion_tokens, tuple(used)
                )

            assert self._executor is not None
            conversation.append(
                ChatMessage("assistant", response.content, tool_calls=response.tool_calls)
            )
            for index, call in enumerate(response.tool_calls):
                if index >= MAX_CALLS_PER_ROUND:
                    result = "Dilewati: terlalu banyak tool call dalam satu putaran."
                else:
                    result = await self._executor.execute(call, ctx)
                    used.append(call.name)
                conversation.append(ChatMessage("tool", result, tool_call_id=call.id))

        raise ProviderUnavailable("model tidak memberi jawaban", retryable=False)

    async def _refund(self, server_id: int, user_id: int, amount: int) -> None:
        try:
            await self._economy.credit(
                server_id, user_id, amount, kind="ai_refund", meta={"reason": "ai_failed"}
            )
        except Exception:
            log.error("refund_failed", server_id=server_id, user_id=user_id, amount=amount)

    async def _load_profile(self, user_id: int) -> tuple[str, bool]:
        async with session_scope(self._sf) as session:
            profile = await UserRepository(session).get_profile(user_id)
            if profile is None:
                return "id", False
            return profile.language, profile.ai_opt_out

    async def _record_usage(
        self,
        *,
        server_id: int,
        user_id: int,
        model: str,
        kind: str,
        status: str = "ok",
        latency_ms: int | None = None,
        tools: tuple[str, ...] = (),
        error_code: str | None = None,
    ) -> None:
        """Catat pemakaian untuk tracking. Kegagalan mencatat tidak boleh mengganggu jawaban."""
        try:
            async with session_scope(self._sf) as session:
                await AIUsageRepository(session).add(
                    server_id=server_id,
                    user_id=user_id,
                    model=model,
                    prompt_tokens=0,
                    completion_tokens=0,
                    coins=0,
                    kind=kind,
                    status=status,
                    latency_ms=latency_ms,
                    tools=tools,
                    error_code=error_code,
                )
        except Exception:
            log.exception("usage_record_failed", server_id=server_id, user_id=user_id)

    def _is_owner(self, user_id: int) -> bool:
        return self._cfg.owner_user_id == user_id

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

    async def _check_quota(self, server_id: int, user_id: int, kind: str) -> None:
        since = self._day_start()
        async with session_scope(self._sf) as session:
            repo = AIUsageRepository(session)
            global_used = await repo.count_since(since)
            user_used = await repo.count_since(since, user_id=user_id)
        if global_used >= self._cfg.daily_global_limit:
            await self._record_rejection(server_id, user_id, kind, "global_quota")
            raise QuotaExceeded("Kuota AI harian bot sudah habis. Coba lagi besok.")
        if user_used >= self._cfg.daily_user_limit:
            await self._record_rejection(server_id, user_id, kind, "user_quota")
            raise QuotaExceeded(
                f"Batas {self._cfg.daily_user_limit} pertanyaan AI per hari sudah tercapai."
            )

    async def _record_rejection(
        self, server_id: int, user_id: int, kind: str, error_code: str
    ) -> None:
        """Catat permintaan yang ditolak karena kuota (tidak menghitung kuota, tidak ada koin)."""
        await self._record_usage(
            server_id=server_id,
            user_id=user_id,
            model="-",
            kind=kind,
            status="rejected",
            error_code=error_code,
        )
