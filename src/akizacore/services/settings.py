from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from akizacore.core.exceptions import NotFound, PermissionDenied, ValidationFailed
from akizacore.database.repositories import SettingsRepository
from akizacore.database.session import session_scope
from akizacore.schemas.settings import FEATURES, SettingsRead, SettingsUpdate

_NOT_REGISTERED = "Server belum terdaftar. Coba ulangi command."


class SettingsService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def get(self, server_id: int) -> SettingsRead:
        async with session_scope(self._sf) as session:
            row = await SettingsRepository(session).get(server_id)
            if row is None:
                raise NotFound(_NOT_REGISTERED)
            return SettingsRead.model_validate(row)

    async def update(self, server_id: int, data: SettingsUpdate) -> SettingsRead:
        values = data.model_dump(exclude_unset=True)
        if "features" in values and values["features"] is not None:
            for feat in values["features"]:
                if feat not in FEATURES:
                    raise ValidationFailed(f"Fitur tidak dikenal: {feat}")
        async with session_scope(self._sf) as session:
            repo = SettingsRepository(session)
            if "features" in values and values["features"] is not None:
                current = await repo.get(server_id)
                if current is None:
                    raise NotFound(_NOT_REGISTERED)
                values["features"] = {**current.features, **values["features"]}
            row = await repo.update(server_id, values)
            if row is None:
                raise NotFound(_NOT_REGISTERED)
            return SettingsRead.model_validate(row)

    async def require_feature(self, server_id: int, feature: str) -> None:
        """Raise PermissionDenied bila modul dimatikan di server ini."""
        data = await self.get(server_id)
        if not data.features.get(feature):
            raise PermissionDenied(
                f"Modul {feature} dimatikan di server ini. "
                "Admin bisa menyalakannya dengan /setup feature."
            )

    async def set_feature(self, server_id: int, feature: str, enabled: bool) -> SettingsRead:
        if feature not in FEATURES:
            raise ValidationFailed(f"Fitur tidak dikenal: {feature}")
        async with session_scope(self._sf) as session:
            repo = SettingsRepository(session)
            current = await repo.get(server_id)
            if current is None:
                raise NotFound(_NOT_REGISTERED)
            merged = {**current.features, feature: enabled}
            row = await repo.update(server_id, {"features": merged})
            if row is None:
                raise NotFound(_NOT_REGISTERED)
            return SettingsRead.model_validate(row)
