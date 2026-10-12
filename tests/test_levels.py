from datetime import UTC

from akizacore.services.levels import level_for_xp, level_progress, xp_for_level
from akizacore.utils.snowflake import snowflake_to_datetime


def test_level_thresholds() -> None:
    assert level_for_xp(0) == 1
    assert level_for_xp(99) == 1
    assert level_for_xp(100) == 2
    assert level_for_xp(399) == 2
    assert level_for_xp(400) == 3


def test_xp_for_level_is_inverse_of_level_for_xp() -> None:
    for level in range(1, 30):
        assert level_for_xp(xp_for_level(level)) == level
        assert level_for_xp(xp_for_level(level) - 1) == max(level - 1, 1)


def test_level_progress() -> None:
    assert level_progress(150) == (2, 50, 300)


def test_snowflake_known_value() -> None:
    created = snowflake_to_datetime(175928847299117063)  # contoh dari dokumentasi Discord
    assert created.tzinfo == UTC
    assert (created.year, created.month, created.day) == (2016, 4, 30)
