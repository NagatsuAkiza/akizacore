import { useState } from 'react'
import { useParams } from 'react-router'
import { useQuery } from '@tanstack/react-query'
import { Loader2 } from 'lucide-react'
import { api } from '../lib/api'
import { PageHeader } from '../components/PageHeader'
import { ErrorAlert } from '../components/ErrorAlert'
import { clsx } from 'clsx'
import type { ModLogEntry, Warning, PaginatedResponse } from '../types'

type Tab = 'logs' | 'warnings'

export function ModerationPage() {
  const { serverId } = useParams<{ serverId: string }>()
  const [tab, setTab] = useState<Tab>('logs')
  const [page, setPage] = useState(1)
  const limit = 20

  const logsQuery = useQuery<PaginatedResponse<ModLogEntry>>({
    queryKey: ['servers', serverId, 'moderation', 'logs', page],
    queryFn: () =>
      api.get<PaginatedResponse<ModLogEntry>>(
        `/servers/${serverId}/moderation/logs?page=${page}&limit=${limit}`,
      ),
    enabled: !!serverId && tab === 'logs',
  })

  const warningsQuery = useQuery<PaginatedResponse<Warning>>({
    queryKey: ['servers', serverId, 'moderation', 'warnings', page],
    queryFn: () =>
      api.get<PaginatedResponse<Warning>>(
        `/servers/${serverId}/moderation/warnings?page=${page}&limit=${limit}`,
      ),
    enabled: !!serverId && tab === 'warnings',
  })

  const activeQuery = tab === 'logs' ? logsQuery : warningsQuery

  return (
    <div className="space-y-6">
      <PageHeader title="Moderation" description="Log moderasi dan peringatan." />

      {/* Tabs */}
      <div className="flex gap-1 rounded-lg bg-gray-800/50 p-1 w-fit">
        {(['logs', 'warnings'] as const).map((t) => (
          <button
            key={t}
            onClick={() => {
              setTab(t)
              setPage(1)
            }}
            className={clsx(
              'rounded-md px-4 py-2 text-sm font-medium transition-colors',
              tab === t
                ? 'bg-gray-700 text-white'
                : 'text-gray-400 hover:text-gray-200',
            )}
          >
            {t === 'logs' ? 'Log Moderasi' : 'Peringatan'}
          </button>
        ))}
      </div>

      {activeQuery.error && (
        <ErrorAlert message="Gagal memuat data." onRetry={() => void activeQuery.refetch()} />
      )}

      {activeQuery.isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-8 w-8 animate-spin text-indigo-500" />
        </div>
      ) : tab === 'logs' ? (
        <LogsTable data={logsQuery.data} page={page} setPage={setPage} />
      ) : (
        <WarningsTable data={warningsQuery.data} page={page} setPage={setPage} />
      )}
    </div>
  )
}

function LogsTable({
  data,
  page,
  setPage,
}: {
  data: PaginatedResponse<ModLogEntry> | undefined
  page: number
  setPage: (fn: (p: number) => number) => void
}) {
  const actionColors: Record<string, string> = {
    warn: 'text-yellow-400 bg-yellow-400/10',
    kick: 'text-orange-400 bg-orange-400/10',
    ban: 'text-red-400 bg-red-400/10',
    timeout: 'text-blue-400 bg-blue-400/10',
    untimeout: 'text-cyan-400 bg-cyan-400/10',
    purge: 'text-purple-400 bg-purple-400/10',
  }

  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900/50 overflow-hidden">
      <table className="w-full">
        <thead>
          <tr className="border-b border-gray-800">
            <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">Aksi</th>
            <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">Moderator</th>
            <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">Target</th>
            <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">Alasan</th>
            <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">Waktu</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-800">
          {data?.items.map((log) => (
            <tr key={log.id} className="hover:bg-gray-800/50 transition-colors">
              <td className="px-4 py-3">
                <span
                  className={clsx(
                    'rounded-full px-2.5 py-0.5 text-xs font-medium',
                    actionColors[log.action] ?? 'text-gray-400 bg-gray-400/10',
                  )}
                >
                  {log.action}
                </span>
              </td>
              <td className="px-4 py-3 text-sm text-gray-300">{log.moderator_name}</td>
              <td className="px-4 py-3 text-sm text-gray-300">{log.target_name}</td>
              <td className="px-4 py-3 text-sm text-gray-400">{log.reason ?? '—'}</td>
              <td className="px-4 py-3 text-sm text-gray-500">
                {new Date(log.created_at).toLocaleString('id-ID')}
              </td>
            </tr>
          ))}
          {data?.items.length === 0 && (
            <tr>
              <td colSpan={5} className="px-4 py-16 text-center text-sm text-gray-500">
                Belum ada log moderasi.
              </td>
            </tr>
          )}
        </tbody>
      </table>

      {data && data.pages > 1 && (
        <div className="flex items-center justify-between border-t border-gray-800 px-4 py-3">
          <p className="text-sm text-gray-400">Halaman {data.page} dari {data.pages}</p>
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
  )
}

function WarningsTable({
  data,
  page,
  setPage,
}: {
  data: PaginatedResponse<Warning> | undefined
  page: number
  setPage: (fn: (p: number) => number) => void
}) {
  return (
    <div className="rounded-xl border border-gray-800 bg-gray-900/50 overflow-hidden">
      <table className="w-full">
        <thead>
          <tr className="border-b border-gray-800">
            <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">User</th>
            <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">Moderator</th>
            <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">Alasan</th>
            <th className="px-4 py-3 text-left text-xs font-medium uppercase text-gray-500">Waktu</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-800">
          {data?.items.map((warning) => (
            <tr key={warning.id} className="hover:bg-gray-800/50 transition-colors">
              <td className="px-4 py-3 text-sm text-white">{warning.username}</td>
              <td className="px-4 py-3 text-sm text-gray-300">{warning.moderator_name}</td>
              <td className="px-4 py-3 text-sm text-gray-400">{warning.reason}</td>
              <td className="px-4 py-3 text-sm text-gray-500">
                {new Date(warning.created_at).toLocaleString('id-ID')}
              </td>
            </tr>
          ))}
          {data?.items.length === 0 && (
            <tr>
              <td colSpan={4} className="px-4 py-16 text-center text-sm text-gray-500">
                Tidak ada peringatan aktif.
              </td>
            </tr>
          )}
        </tbody>
      </table>

      {data && data.pages > 1 && (
        <div className="flex items-center justify-between border-t border-gray-800 px-4 py-3">
          <p className="text-sm text-gray-400">Halaman {data.page} dari {data.pages}</p>
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
  )
}
