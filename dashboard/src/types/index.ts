/** User info returned by GET /auth/me */
export interface User {
  id: string
  username: string
  discriminator: string
  avatar: string | null
  global_name: string | null
}

/** Guild returned by GET /servers */
export interface Server {
  id: string
  name: string
  icon: string | null
  owner: boolean
  bot_active: boolean
}

/** Server stats from GET /servers/{id}/stats */
export interface ServerStats {
  member_count: number
  total_messages: number
  ai_queries_today: number
  economy_transactions_today: number
  active_warnings: number
  mod_actions_today: number
}

/** Server settings from GET /servers/{id}/settings */
export interface ServerSettings {
  server_id: string
  prefix: string
  log_channel_id: string | null
  welcome_channel_id: string | null
  welcome_message: string | null
  features: Record<string, boolean>
}

/** Economy leaderboard entry */
export interface LeaderboardEntry {
  user_id: string
  username: string
  balance: number
  level: number
  xp: number
  rank: number
}

/** Moderation log entry */
export interface ModLogEntry {
  id: number
  action: string
  moderator_id: string
  moderator_name: string
  target_id: string
  target_name: string
  reason: string | null
  created_at: string
}

/** Warning entry */
export interface Warning {
  id: number
  user_id: string
  username: string
  moderator_id: string
  moderator_name: string
  reason: string
  created_at: string
}

/** Paginated response wrapper */
export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  limit: number
  pages: number
}
