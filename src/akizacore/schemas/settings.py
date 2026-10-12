from pydantic import BaseModel, ConfigDict, field_validator

FEATURES: tuple[str, ...] = ("ai", "economy", "fun", "utility", "moderation")

# AI default mati: admin harus menyalakan sendiri (kontrol biaya)
DEFAULT_FEATURES: dict[str, bool] = {
    "ai": False,
    "economy": True,
    "fun": True,
    "utility": True,
    "moderation": True,
}


class SettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    server_id: int
    log_channel_id: int | None = None
    welcome_channel_id: int | None = None
    autorole_id: int | None = None
    ai_persona: str | None = None
    features: dict[str, bool] = {}

    @field_validator("features")
    @classmethod
    def _merge_defaults(cls, value: dict[str, bool]) -> dict[str, bool]:
        # fitur baru yang belum tersimpan di DB otomatis memakai nilai default
        return {**DEFAULT_FEATURES, **value}


class SettingsUpdate(BaseModel):
    """Hanya field yang diisi yang diubah (gunakan model_dump(exclude_unset=True))."""

    log_channel_id: int | None = None
    welcome_channel_id: int | None = None
    autorole_id: int | None = None
    ai_persona: str | None = None
