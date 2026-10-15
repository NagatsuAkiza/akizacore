import random
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from akizacore.ai.config import AIConfig
from akizacore.ai.orchestrator import AIOrchestrator
from akizacore.ai.providers.base import LLMProvider
from akizacore.ai.tools.builtin import build_default_registry
from akizacore.services.ai_usage import AIUsageService
from akizacore.services.auth import AuthService
from akizacore.services.economy import EconomyService
from akizacore.services.economy_config import EconomyConfig
from akizacore.services.memory import MemoryService
from akizacore.services.moderation import ModerationService
from akizacore.services.onboarding import OnboardingService
from akizacore.services.settings import SettingsService
from akizacore.services.shop import ShopService
from akizacore.services.stats import StatsService


@dataclass(frozen=True)
class Services:
    """Kumpulan service. Dipakai bot sekarang dan FastAPI di Fase 6."""

    onboarding: OnboardingService
    settings: SettingsService
    economy: EconomyService
    shop: ShopService
    stats: StatsService
    moderation: ModerationService
    memory: MemoryService
    auth: AuthService
    usage: AIUsageService
    ai: AIOrchestrator | None  # None bila provider AI belum dikonfigurasi

    @classmethod
    def build(
        cls,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        llm: LLMProvider | None = None,
        ai_config: AIConfig | None = None,
        economy_config: EconomyConfig | None = None,
        owner_user_id: int | None = None,
        starter_balance: int | None = None,
        clock: Callable[[], datetime] | None = None,
        rng: random.Random | None = None,
    ) -> Self:
        eco_cfg = economy_config or EconomyConfig()
        if owner_user_id is not None:
            eco_cfg = replace(eco_cfg, owner_user_id=owner_user_id)
        if starter_balance is not None:
            eco_cfg = replace(eco_cfg, starter_balance=starter_balance)
        ai_cfg = ai_config or AIConfig()
        if owner_user_id is not None:
            ai_cfg = replace(ai_cfg, owner_user_id=owner_user_id)

        settings = SettingsService(session_factory)
        economy = EconomyService(session_factory, config=eco_cfg, clock=clock, rng=rng)
        shop = ShopService(session_factory, economy=economy)
        stats = StatsService(session_factory, utc_offset_hours=ai_cfg.utc_offset_hours)
        moderation = ModerationService(session_factory)
        memory = MemoryService(session_factory)

        ai: AIOrchestrator | None = None
        if llm is not None:
            tools = (
                build_default_registry(economy=economy, shop=shop, stats=stats)
                if ai_cfg.tools_enabled
                else None
            )
            ai = AIOrchestrator(
                session_factory,
                llm=llm,
                economy=economy,
                settings=settings,
                memory=memory,
                config=ai_cfg,
                tools=tools,
            )
        return cls(
            onboarding=OnboardingService(session_factory),
            settings=settings,
            economy=economy,
            shop=shop,
            stats=stats,
            moderation=moderation,
            memory=memory,
            auth=AuthService(session_factory),
            usage=AIUsageService(
                session_factory,
                daily_user_limit=ai_cfg.daily_user_limit,
                daily_global_limit=ai_cfg.daily_global_limit,
                utc_offset_hours=ai_cfg.utc_offset_hours,
                retention_days=ai_cfg.usage_retention_days,
            ),
            ai=ai,
        )
