import { AlertTriangle } from 'lucide-react'

interface ErrorAlertProps {
  message: string
  onRetry?: () => void
}

export function ErrorAlert({ message, onRetry }: ErrorAlertProps) {
  return (
    <div className="rounded-lg border border-red-900/50 bg-red-950/30 p-4">
      <div className="flex items-start gap-3">
        <AlertTriangle className="h-5 w-5 text-red-400 mt-0.5" />
        <div className="flex-1">
          <p className="text-sm font-medium text-red-300">Error</p>
          <p className="mt-1 text-sm text-red-400/80">{message}</p>
          {onRetry && (
            <button
              onClick={onRetry}
              className="mt-3 rounded-md bg-red-900/40 px-3 py-1.5 text-xs font-medium text-red-300 hover:bg-red-900/60 transition-colors"
            >
              Coba lagi
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
