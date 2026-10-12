import random
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from akizacore.ai.config import AIConfig
from akizacore.ai.orchestrator import AIOrchestrator
from akizacore.ai.providers.base import LLMProvider
from akizacore.services.economy import EconomyService
from akizacore.services.economy_config import EconomyConfig
from akizacore.services.onboarding import OnboardingService
from akizacore.services.settings import SettingsService


@dataclass(frozen=True)
class Services:
    """Kumpulan service. Dipakai bot sekarang dan FastAPI di Fase 6."""

    onboarding: OnboardingService
    settings: SettingsService
    economy: EconomyService
    ai: AIOrchestrator | None  # None bila provider AI belum dikonfigurasi

    @classmethod
    def build(
        cls,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        llm: LLMProvider | None = None,
        ai_config: AIConfig | None = None,
        economy_config: EconomyConfig | None = None,
        starter_balance: int | None = None,
        clock: Callable[[], datetime] | None = None,
        rng: random.Random | None = None,
    ) -> Self:
        eco_cfg = economy_config or EconomyConfig()
        if starter_balance is not None:
            eco_cfg = replace(eco_cfg, starter_balance=starter_balance)
        settings = SettingsService(session_factory)
        economy = EconomyService(session_factory, config=eco_cfg, clock=clock, rng=rng)
        ai = (
            AIOrchestrator(
                session_factory,
                llm=llm,
                economy=economy,
                settings=settings,
                config=ai_config or AIConfig(),
            )
            if llm is not None
            else None
        )
        return cls(
            onboarding=OnboardingService(session_factory),
            settings=settings,
            economy=economy,
            ai=ai,
        )
