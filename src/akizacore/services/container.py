from dataclasses import dataclass
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from akizacore.services.onboarding import OnboardingService
from akizacore.services.settings import SettingsService


@dataclass(frozen=True)
class Services:
    """Kumpulan service. Dipakai bot sekarang dan FastAPI di Fase 6."""

    onboarding: OnboardingService
    settings: SettingsService

    @classmethod
    def build(cls, session_factory: async_sessionmaker[AsyncSession]) -> Self:
        return cls(
            onboarding=OnboardingService(session_factory),
            settings=SettingsService(session_factory),
        )
