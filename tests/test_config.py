import pytest

from akizacore.config.settings import Settings


def test_owner_user_id_has_no_hardcoded_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OWNER_USER_ID", raising=False)
    s = Settings(_env_file=None, discord_token="dummy")  # type: ignore[call-arg]
    assert s.owner_user_id is None


def test_owner_user_id_is_read_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OWNER_USER_ID", "12345")
    s = Settings(_env_file=None, discord_token="dummy")  # type: ignore[call-arg]
    assert s.owner_user_id == 12345


def test_settings_defaults() -> None:
    s = Settings(_env_file=None, discord_token="dummy")  # type: ignore[call-arg]
    assert s.environment == "dev"
    assert s.dev_guild_id is None
    assert s.discord_token.get_secret_value() == "dummy"
