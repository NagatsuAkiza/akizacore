from pydantic import BaseModel


class StatsView(BaseModel):
    economy_accounts: int
    coins_in_circulation: int
    ai_requests_today: int
    ai_requests_7d: int
