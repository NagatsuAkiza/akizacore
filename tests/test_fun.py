import pytest

from akizacore.cogs.fun.basic import REACTIONS, PollState, parse_poll_options


def test_parse_poll_options_strips_values_and_ignores_empty_optional_values() -> None:
    assert parse_poll_options(" Ya ", "Tidak", " ", None, " Mungkin ") == [
        "Ya",
        "Tidak",
        "Mungkin",
    ]


def test_parse_poll_options_rejects_duplicate_values() -> None:
    with pytest.raises(ValueError, match="duplikat"):
        parse_poll_options("Ya", "ya")


def test_parse_poll_options_requires_two_values() -> None:
    with pytest.raises(ValueError, match="setidaknya dua"):
        parse_poll_options("Ya", " ")


def test_poll_state_allows_a_user_to_change_vote() -> None:
    state = PollState(["Ya", "Tidak"], {})

    state.vote(10, 0)
    state.vote(20, 1)
    state.vote(10, 1)

    assert state.counts() == [0, 2]


def test_reactions_are_limited_to_curated_emojis() -> None:
    assert REACTIONS["happy"] == "🎉"
    assert "custom" not in REACTIONS
