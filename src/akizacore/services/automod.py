import re
from collections import defaultdict, deque
from collections.abc import Callable, Sequence
from time import monotonic
from urllib.parse import urlparse

_URL_RE = re.compile(
    r"(?:https?://|www\.)[^\s<>]+|(?:discord\.gg|discord\.com/invite)/[A-Za-z0-9-]+",
    re.IGNORECASE,
)


def _host(raw: str) -> str:
    url = raw if "://" in raw else "https://" + raw
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def find_blocked_links(text: str, allowed: Sequence[str]) -> list[str]:
    """Kembalikan domain pada `text` yang tidak ada di daftar `allowed` (subdomain ikut diizinkan)."""
    allowed_hosts = {a.strip().lower().removeprefix("www.") for a in allowed if a.strip()}
    blocked: list[str] = []
    for match in _URL_RE.findall(text):
        host = _host(match)
        if not host:
            continue
        if any(host == a or host.endswith("." + a) for a in allowed_hosts):
            continue
        blocked.append(host)
    return list(dict.fromkeys(blocked))


class SpamTracker:
    """Penghitung pesan beruntun per (server, user) dengan jendela waktu geser. Di memori."""

    def __init__(self, *, clock: Callable[[], float] = monotonic) -> None:
        self._clock = clock
        self._hits: defaultdict[tuple[int, int], deque[float]] = defaultdict(deque)

    def hit(self, server_id: int, user_id: int, *, limit: int, window_s: float) -> bool:
        """Catat satu pesan. True bila batas tercapai (hitungan di-reset setelahnya)."""
        now = self._clock()
        if len(self._hits) > 10_000:
            self._prune(now)
        queue = self._hits[(server_id, user_id)]
        queue.append(now)
        while queue and now - queue[0] > window_s:
            queue.popleft()
        if len(queue) >= limit:
            queue.clear()
            return True
        return False

    def _prune(self, now: float) -> None:
        stale = [key for key, queue in self._hits.items() if not queue or now - queue[-1] > 60]
        for key in stale:
            del self._hits[key]
