from pydantic import BaseModel


class StatsView(BaseModel):
    economy_accounts: int
    coins_in_circulation: int
    ai_requests_today: int
    ai_requests_7d: int
    member_count: int = 0
    total_messages: int = 0
    ai_queries_today: int = 0
    economy_transactions_today: int = 0
    active_warnings: int = 0
    mod_actions_today: int = 0
