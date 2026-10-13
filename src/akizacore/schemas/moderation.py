from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class WarningView:
    id: int
    mod_id: int
    reason: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class WarnResult:
    warning_id: int
    total: int
    escalate: bool  # True bila jumlah warn aktif sudah mencapai ambang auto-timeout


@dataclass(frozen=True, slots=True)
class ModLogView:
    id: int
    target_id: int
    mod_id: int | None
    action: str
    reason: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class AutomodView:
    server_id: int
    anti_spam: bool = False
    spam_messages: int = 5
    spam_window_s: int = 8
    anti_link: bool = False
    allowed_domains: tuple[str, ...] = ()
    action: str = "delete"
    timeout_minutes: int = 10


@dataclass(frozen=True, slots=True)
class ModLogDetailView:
    id: int
    server_id: int
    target_id: int
    target_name: str
    mod_id: int | None
    mod_name: str
    action: str
    reason: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class WarningDetailView:
    id: int
    server_id: int
    user_id: int
    username: str
    mod_id: int
    mod_name: str
    reason: str
    created_at: datetime
