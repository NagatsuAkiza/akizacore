from akizacore.config.settings import Settings


def test_settings_defaults() -> None:
    s = Settings(_env_file=None, discord_token="dummy")  # type: ignore[call-arg]
    assert s.environment == "dev"
    assert s.dev_guild_id is None
    assert s.discord_token.get_secret_value() == "dummy"
