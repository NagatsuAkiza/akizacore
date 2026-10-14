from datetime import date, datetime

from pydantic import BaseModel


class UsageTotals(BaseModel):
    requests: int = 0  # panggilan LLM yang berhasil (/ask, mention, /translate)
    rule_hits: int = 0  # dijawab rule router tanpa LLM
    errors: int = 0  # panggilan gagal (koin di-refund)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    coins: int = 0
    avg_latency_ms: int | None = None
    p95_latency_ms: int | None = None


class DailyUsage(BaseModel):
    day: date
    requests: int = 0
    errors: int = 0
    tokens: int = 0
    coins: int = 0


class UserUsage(BaseModel):
    user_id: str
    username: str | None = None
    requests: int
    tokens: int
    coins: int


class NamedCount(BaseModel):
    name: str
    requests: int
    tokens: int = 0


class ErrorEntry(BaseModel):
    id: int
    created_at: datetime
    user_id: str
    kind: str
    error_code: str | None = None
    latency_ms: int | None = None


class ServerUsageReport(BaseModel):
    days: int
    since: datetime
    totals: UsageTotals
    daily: list[DailyUsage]
    top_users: list[UserUsage]
    by_model: list[NamedCount]
    by_kind: list[NamedCount]
    tools: list[NamedCount]
    recent_errors: list[ErrorEntry]


class MyUsage(BaseModel):
    used_today: int
    user_limit: int
    global_used_today: int
    global_limit: int
    tokens_today: int
    coins_today: int
    last_7_days: UsageTotals
