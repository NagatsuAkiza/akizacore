import type { LucideIcon } from 'lucide-react'
import { clsx } from 'clsx'

interface StatCardProps {
  label: string
  value: string | number
  icon: LucideIcon
  trend?: 'up' | 'down' | 'neutral'
  className?: string
}

export function StatCard({ label, value, icon: Icon, trend, className }: StatCardProps) {
  return (
    <div
      className={clsx(
        'rounded-xl border border-gray-800 bg-gray-900/50 p-5 transition-colors hover:border-gray-700',
        className,
      )}
    >
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium text-gray-400">{label}</p>
        <Icon className="h-5 w-5 text-gray-500" />
      </div>
      <p className="mt-2 text-2xl font-bold text-white">{value}</p>
      {trend && (
        <p
          className={clsx('mt-1 text-xs font-medium', {
            'text-green-400': trend === 'up',
            'text-red-400': trend === 'down',
            'text-gray-500': trend === 'neutral',
          })}
        >
          {trend === 'up' ? '↑' : trend === 'down' ? '↓' : '—'}
        </p>
      )}
    </div>
  )
}
