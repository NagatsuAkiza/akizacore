/** Cermin schemas/ai_usage.py di backend (GET /servers/{id}/ai/usage). */

export interface UsageTotals {
  requests: number
  rule_hits: number
  errors: number
  rejected: number
  prompt_tokens: number
  completion_tokens: number
  coins: number
  avg_latency_ms: number | null
  p95_latency_ms: number | null
}

export interface DailyUsage {
  /** Tanggal lokal (zona waktu kuota), format YYYY-MM-DD */
  day: string
  requests: number
  errors: number
  tokens: number
  coins: number
}

export interface UserUsage {
  user_id: string
  username: string | null
  requests: number
  tokens: number
  coins: number
}

export interface NamedCount {
  name: string
  requests: number
  tokens: number
}

export interface UsageError {
  id: number
  created_at: string
  user_id: string
  kind: string
  error_code: string | null
  latency_ms: number | null
}

export interface ServerUsageReport {
  days: number
  since: string
  totals: UsageTotals
  daily: DailyUsage[]
  top_users: UserUsage[]
  by_model: NamedCount[]
  by_kind: NamedCount[]
  tools: NamedCount[]
  recent_errors: UsageError[]
}