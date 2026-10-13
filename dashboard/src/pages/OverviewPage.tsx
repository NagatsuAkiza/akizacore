import { useParams } from 'react-router'
import {
  Users,
  MessageSquare,
  Brain,
  Coins,
  AlertTriangle,
  Shield,
  Loader2,
} from 'lucide-react'
import { useServerStats } from '../hooks/useServerStats'
import { PageHeader } from '../components/PageHeader'
import { StatCard } from '../components/StatCard'
import { ErrorAlert } from '../components/ErrorAlert'

export function OverviewPage() {
  const { serverId } = useParams<{ serverId: string }>()
  const { data: stats, isLoading, error, refetch } = useServerStats(serverId!)

  return (
    <div className="space-y-6">
      <PageHeader
        title="Overview"
        description="Ringkasan aktivitas server."
      />

      {error && (
        <ErrorAlert message="Gagal memuat statistik." onRetry={() => void refetch()} />
      )}

      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader2 className="h-8 w-8 animate-spin text-indigo-500" />
        </div>
      ) : stats ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <StatCard label="Members" value={stats.member_count.toLocaleString()} icon={Users} />
          <StatCard label="Total Pesan" value={stats.total_messages.toLocaleString()} icon={MessageSquare} />
          <StatCard label="AI Queries Hari Ini" value={stats.ai_queries_today} icon={Brain} />
          <StatCard label="Transaksi Hari Ini" value={stats.economy_transactions_today} icon={Coins} />
          <StatCard label="Warning Aktif" value={stats.active_warnings} icon={AlertTriangle} />
          <StatCard label="Aksi Moderasi Hari Ini" value={stats.mod_actions_today} icon={Shield} />
        </div>
      ) : null}
    </div>
  )
}
