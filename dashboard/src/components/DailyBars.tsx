import type { DailyUsage } from '../types/aiUsage'

interface DailyBarsProps {
  data: DailyUsage[]
}

function formatDay(iso: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString('id-ID', { day: 'numeric', month: 'short' })
}

/** Grafik batang harian: biru = pertanyaan berhasil, merah = gagal. CSS murni. */
export function DailyBars({ data }: DailyBarsProps) {
  const max = Math.max(1, ...data.map((d) => d.requests + d.errors))
  const first = data[0]
  const last = data[data.length - 1]

  return (
    <div>
      <div className="flex h-40 items-end gap-1" role="img" aria-label="Grafik pemakaian AI per hari">
        {data.map((d) => {
          const total = d.requests + d.errors
          const height = total === 0 ? 2 : Math.max(4, Math.round((total / max) * 100))
          const errorShare = total === 0 ? 0 : (d.errors / total) * 100
          return (
            <div
              key={d.day}
              className="flex h-full flex-1 flex-col justify-end"
              title={`${formatDay(d.day)}: ${d.requests} pertanyaan, ${d.errors} gagal, ${d.tokens.toLocaleString('id-ID')} token`}
            >
              <div
                className={`flex w-full flex-col overflow-hidden rounded-t ${total === 0 ? 'bg-gray-800' : 'bg-indigo-500/80'}`}
                style={{ height: `${height}%` }}
              >
                {d.errors > 0 && <div className="bg-red-500/90" style={{ height: `${errorShare}%` }} />}
              </div>
            </div>
          )
        })}
      </div>
      {first && last && (
        <div className="mt-2 flex justify-between text-xs text-gray-500">
          <span>{formatDay(first.day)}</span>
          <span>{formatDay(last.day)}</span>
        </div>
      )}
    </div>
  )
}