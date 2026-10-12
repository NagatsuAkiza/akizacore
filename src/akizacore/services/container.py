from dataclasses import dataclass
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from akizacore.services.economy import EconomyService
from akizacore.services.onboarding import OnboardingService
from akizacore.services.settings import SettingsService


@dataclass(frozen=True)
class Services:
    """Kumpulan service. Dipakai bot sekarang dan FastAPI di Fase 6."""

    onboarding: OnboardingService
    settings: SettingsService
    economy: EconomyService

    @classmethod
    def build(
        cls, session_factory: async_sessionmaker[AsyncSession], *, starter_balance: int = 100
    ) -> Self:
        return cls(
            onboarding=OnboardingService(session_factory),
            settings=SettingsService(session_factory),
            economy=EconomyService(session_factory, starter_balance=starter_balance),
        )
