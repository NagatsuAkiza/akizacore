import { useState } from 'react'
import { useParams } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import { Trophy, Loader2 } from 'lucide-react'
import { api } from '../lib/api'
import { PageHeader } from '../components/PageHeader'
import { ErrorAlert } from '../components/ErrorAlert'
import type { LeaderboardEntry, PaginatedResponse } from '../types'

export function EconomyPage() {
  const { serverId } = useParams<{ serverId: string }>()
  const [page, setPage] = useState(1)
  const limit = 20

  const { data, isLoading, error, refetch } = useQuery<PaginatedResponse<LeaderboardEntry>>({
    queryKey: ['servers', serverId, 'economy', 'leaderboard', page],
    queryFn: () =>
      api.get<PaginatedResponse<LeaderboardEntry>>(
        `/servers/${serverId}/economy/leaderboard?page=${page}&limit=${limit}`,
      ),
    enabled: !!serverId,
  })

  return (
    <div className="space-y-6">
      <PageHeader
        title="Economy"
        description="Leaderboard dan statistik ekonomi server."
      />

      {error && (
        <ErrorAlert message="Gagal memuat leaderboard." onRetry={() => void refetch()} />
      )}

      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-8 w-8 animate-spin text-indigo-500" />
        </div>
      ) : (
        <div className="rounded-xl border border-gray-800 bg-gray-900/50 overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-gray-800">
                <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">
                  Rank
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">
                  User
                </th>
                <th className="px-4 py-3 text-right text-xs font-medium uppercase text-gray-500">
                  Balance
                </th>
                <th className="px-4 py-3 text-right text-xs font-medium uppercase text-gray-500">
                  Level
                </th>
                <th className="px-4 py-3 text-right text-xs font-medium uppercase text-gray-500">
                  XP
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800">
              {data?.items.map((entry) => (
                <tr key={entry.user_id} className="hover:bg-gray-800/50 transition-colors">
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      {entry.rank <= 3 && (
                        <Trophy
                          className={`h-4 w-4 ${
                            entry.rank === 1
                              ? 'text-yellow-400'
                              : entry.rank === 2
                                ? 'text-gray-300'
                                : 'text-amber-600'
                          }`}
                        />
                      )}
                      <span className="text-sm font-medium text-gray-300">#{entry.rank}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-sm font-medium text-white">{entry.username}</td>
                  <td className="px-4 py-3 text-right text-sm text-gray-300">
                    {entry.balance.toLocaleString()} 🪙
                  </td>
                  <td className="px-4 py-3 text-right text-sm text-gray-300">{entry.level}</td>
                  <td className="px-4 py-3 text-right text-sm text-gray-300">
                    {entry.xp.toLocaleString()}
                  </td>
                </tr>
              ))}
              {data?.items.length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-16 text-center text-sm text-gray-500">
                    Belum ada data ekonomi.
                  </td>
                </tr>
              )}
            </tbody>
          </table>

          {data && data.pages > 1 && (
            <div className="flex items-center justify-between border-t border-gray-800 px-4 py-3">
              <p className="text-sm text-gray-400">
                Halaman {data.page} dari {data.pages}
              </p>
              <div className="flex gap-2">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page === 1}
                  className="rounded-lg border border-gray-700 px-3 py-1.5 text-sm text-gray-300 hover:bg-gray-800 disabled:opacity-50 transition-colors"
                >
                  Sebelumnya
                </button>
                <button
                  onClick={() => setPage((p) => Math.min(data.pages, p + 1))}
                  disabled={page >= data.pages}
                  className="rounded-lg border border-gray-700 px-3 py-1.5 text-sm text-gray-300 hover:bg-gray-800 disabled:opacity-50 transition-colors"
                >
                  Berikutnya
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
