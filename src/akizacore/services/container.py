from dataclasses import dataclass
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from akizacore.ai.config import AIConfig
from akizacore.ai.orchestrator import AIOrchestrator
from akizacore.ai.providers.base import LLMProvider
from akizacore.services.economy import EconomyService
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
        starter_balance: int = 100,
    ) -> Self:
        settings = SettingsService(session_factory)
        economy = EconomyService(session_factory, starter_balance=starter_balance)
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
