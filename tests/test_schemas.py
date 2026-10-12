from akizacore.schemas.settings import DEFAULT_FEATURES, SettingsRead, SettingsUpdate


def test_features_merge_with_defaults() -> None:
    data = SettingsRead(server_id=1, features={"ai": True})
    assert data.features["ai"] is True
    assert data.features["economy"] is True
    assert set(data.features) == set(DEFAULT_FEATURES)


def test_update_only_dumps_provided_fields() -> None:
    update = SettingsUpdate(log_channel_id=123)
    assert update.model_dump(exclude_unset=True) == {"log_channel_id": 123}
