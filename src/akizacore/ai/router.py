"""Intent router tahap 2: aturan murah untuk pertanyaan umum, tanpa LLM dan tanpa potong koin.

Hanya cocok bila SELURUH pesan berbentuk pertanyaan sederhana (fullmatch), supaya kalimat seperti
"jelaskan konsep koin kripto" tidak salah dibelokkan.
"""

import re
from dataclasses import dataclass

_PRONOUN = r"(?: (?:ku|saya|aku|gue|gw))?"

_BALANCE = tuple(
    re.compile(pattern)
    for pattern in (
        rf"(?:berapa )?(?:saldo|koin)(?:ku)?{_PRONOUN}",
        rf"(?:cek|lihat|liat|tampilkan) (?:saldo|koin)(?:ku)?{_PRONOUN}",
        rf"(?:saldo|koin)(?:ku)?{_PRONOUN} (?:berapa|brp)",
        r"(?:my )?(?:balance|coins)",
        r"how (?:much|many) (?:money|coins)(?: do i have)?",
    )
)

_LEADERBOARD_XP = tuple(
    re.compile(pattern) for pattern in (r"(?:leaderboard|peringkat|ranking|top) (?:xp|level)",)
)

_LEADERBOARD_BALANCE = tuple(
    re.compile(pattern)
    for pattern in (
        r"(?:leaderboard|peringkat|ranking)(?: koin| saldo)?",
        r"siapa (?:yang )?(?:paling )?kaya",
    )
)


@dataclass(frozen=True)
class RuleMatch:
    tool: str
    args: dict[str, object]


def normalize(text: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", text.lower()).split())


def _matches(patterns: tuple[re.Pattern[str], ...], text: str) -> bool:
    return any(pattern.fullmatch(text) for pattern in patterns)


def match_rule(text: str) -> RuleMatch | None:
    normalized = normalize(text)
    if not normalized:
        return None
    if _matches(_BALANCE, normalized):
        return RuleMatch("get_balance", {})
    if _matches(_LEADERBOARD_XP, normalized):
        return RuleMatch("get_leaderboard", {"by": "xp"})
    if _matches(_LEADERBOARD_BALANCE, normalized):
        return RuleMatch("get_leaderboard", {"by": "balance"})
    return None
