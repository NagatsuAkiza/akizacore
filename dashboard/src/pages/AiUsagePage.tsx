import { useState } from 'react'
import { useParams } from 'react-router'
import { Bot, Coins, Loader2, Sparkles, Timer, TriangleAlert, Zap } from 'lucide-react'
import { clsx } from 'clsx'
import { useAiUsage } from '../hooks/useAiUsage'
import { PageHeader } from '../components/PageHeader'
import { StatCard } from '../components/StatCard'
import { ErrorAlert } from '../components/ErrorAlert'
import { DailyBars } from '../components/DailyBars'
import type { NamedCount } from '../types/aiUsage'

const RANGES = [7, 14, 30] as const

const KIND_LABELS: Record<string, string> = {
  ask: 'Tanya (/ask, mention)',
  translate: 'Terjemahan',
  rule: 'Dijawab tanpa AI',
}

function n(value: number): string {
  return value.toLocaleString('id-ID')
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-xl border border-gray-800 bg-gray-900/50 p-5">
      <h2 className="mb-3 text-sm font-semibold text-gray-300">{title}</h2>
      {children}
    </section>
  )
}

function CountList({ rows, labels }: { rows: NamedCount[]; labels?: Record<string, string> }) {
  if (rows.length === 0) return <p className="text-sm text-gray-500">Belum ada data.</p>
  return (
    <ul className="divide-y divide-gray-800">
      {rows.map((row) => (
        <li key={row.name} className="flex items-center justify-between py-2 text-sm">
          <span className="truncate text-gray-300">{labels?.[row.name] ?? row.name}</span>
          <span className="ml-3 shrink-0 font-medium text-white">{n(row.requests)}</span>
        </li>
      ))}
    </ul>
  )
}

export function AiUsagePage() {
  const { serverId } = useParams<{ serverId: string }>()
  const [days, setDays] = useState<number>(7)
  const { data, isLoading, error, refetch } = useAiUsage(serverId!, days)

  const totals = data?.totals
  const latency =
    totals?.avg_latency_ms != null
      ? `${n(totals.avg_latency_ms)} ms (p95 ${n(totals.p95_latency_ms ?? 0)})`
      : '-'

  return (
    <div className="space-y-6">
      <PageHeader title="AI Usage" description="Pemakaian AI di server ini: volume, token, biaya koin, dan error.">
        <div className="flex rounded-lg border border-gray-800 bg-gray-900/50 p-1">
          {RANGES.map((range) => (
            <button
              key={range}
              onClick={() => setDays(range)}
              className={clsx(
                'rounded-md px-3 py-1 text-sm font-medium transition-colors',
                days === range ? 'bg-indigo-600/30 text-indigo-300' : 'text-gray-400 hover:text-gray-200',
              )}
            >
              {range} hari
            </button>
          ))}
        </div>
      </PageHeader>

      {error && <ErrorAlert message="Gagal memuat data pemakaian AI." onRetry={() => void refetch()} />}

      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-8 w-8 animate-spin text-indigo-500" />
        </div>
      ) : data && totals ? (
        <>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <StatCard label="Pertanyaan" value={n(totals.requests)} icon={Bot} />
            <StatCard label="Dijawab tanpa AI" value={n(totals.rule_hits)} icon={Sparkles} />
            <StatCard label="Gagal" value={n(totals.errors)} icon={TriangleAlert} />
            <StatCard
              label="Token (prompt + jawaban)"
              value={n(totals.prompt_tokens + totals.completion_tokens)}
              icon={Zap}
            />
            <StatCard label="Koin terpakai" value={n(totals.coins)} icon={Coins} />
            <StatCard label="Latensi rata-rata" value={latency} icon={Timer} />
          </div>

          <Panel title={`Pertanyaan per hari (${data.days} hari)`}>
            <DailyBars data={data.daily} />
            <p className="mt-3 text-xs text-gray-500">
              Biru: berhasil. Merah: gagal (koin dikembalikan). Arahkan kursor ke batang untuk detail.
            </p>
          </Panel>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Panel title="Pemakai teratas">
              {data.top_users.length === 0 ? (
                <p className="text-sm text-gray-500">Belum ada data.</p>
              ) : (
                <ul className="divide-y divide-gray-800">
                  {data.top_users.map((user, index) => (
                    <li key={user.user_id} className="flex items-center justify-between py-2 text-sm">
                      <span className="truncate text-gray-300">
                        {index + 1}. {user.username ?? user.user_id}
                      </span>
                      <span className="ml-3 shrink-0 text-gray-400">
                        <span className="font-medium text-white">{n(user.requests)}</span> pertanyaan,{' '}
                        {n(user.tokens)} token
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </Panel>
            <Panel title="Jenis permintaan">
              <CountList rows={data.by_kind} labels={KIND_LABELS} />
            </Panel>
            <Panel title="Model">
              <CountList rows={data.by_model} />
            </Panel>
            <Panel title="Tool yang dipakai AI">
              <CountList rows={data.tools} />
            </Panel>
          </div>

          <Panel title="Error terakhir">
            {data.recent_errors.length === 0 ? (
              <p className="text-sm text-gray-500">Tidak ada error pada rentang ini.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-800 text-left text-xs uppercase text-gray-500">
                      <th className="py-2 pr-4 font-medium">Waktu</th>
                      <th className="py-2 pr-4 font-medium">Jenis</th>
                      <th className="py-2 pr-4 font-medium">Kode error</th>
                      <th className="py-2 pr-4 text-right font-medium">Durasi</th>
                      <th className="py-2 font-medium">User ID</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-800">
                    {data.recent_errors.map((entry) => (
                      <tr key={entry.id}>
                        <td className="py-2 pr-4 text-gray-300">
                          {new Date(entry.created_at).toLocaleString('id-ID')}
                        </td>
                        <td className="py-2 pr-4 text-gray-300">{entry.kind}</td>
                        <td className="py-2 pr-4 text-red-300">{entry.error_code ?? '-'}</td>
                        <td className="py-2 pr-4 text-right text-gray-400">
                          {entry.latency_ms != null ? `${n(entry.latency_ms)} ms` : '-'}
                        </td>
                        <td className="py-2 font-mono text-xs text-gray-500">{entry.user_id}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>
        </>
      ) : null}
    </div>
  )
}