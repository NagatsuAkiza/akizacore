from akizacore.services.automod import SpamTracker, find_blocked_links


def test_blocks_unknown_domain() -> None:
    assert find_blocked_links("lihat https://evil.com/x", []) == ["evil.com"]


def test_allows_domain_and_subdomain() -> None:
    text = "https://youtu.be/a https://www.example.org/p https://cdn.example.org/y"
    assert find_blocked_links(text, ["example.org", "youtu.be"]) == []


def test_discord_invite_is_blocked_by_default() -> None:
    assert find_blocked_links("join discord.gg/abc123", []) == ["discord.gg"]


def test_plain_text_is_ok() -> None:
    assert find_blocked_links("halo semuanya, apa kabar?", []) == []


def test_spam_tracker_triggers_at_limit() -> None:
    now = [0.0]
    tracker = SpamTracker(clock=lambda: now[0])
    for _ in range(4):
        assert tracker.hit(1, 2, limit=5, window_s=8) is False
        now[0] += 1
    assert tracker.hit(1, 2, limit=5, window_s=8) is True
    assert tracker.hit(1, 2, limit=5, window_s=8) is False  # reset setelah terpicu


def test_spam_tracker_window_expires() -> None:
    now = [0.0]
    tracker = SpamTracker(clock=lambda: now[0])
    for _ in range(10):
        assert tracker.hit(1, 2, limit=3, window_s=5) is False
        now[0] += 6  # selalu di luar jendela
