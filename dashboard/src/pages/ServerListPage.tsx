import { useNavigate } from 'react-router'
import { Bot, ArrowRight } from 'lucide-react'
import { useServers } from '../hooks/useServers'
import { useAuth } from '../hooks/useAuth'
import { LoadingScreen } from '../components/LoadingScreen'
import { ErrorAlert } from '../components/ErrorAlert'
import { UserMenu } from '../components/UserMenu'
import type { Server } from '../types'

function serverIcon(server: Server) {
  if (server.icon) {
    return `https://cdn.discordapp.com/icons/${server.id}/${server.icon}.webp?size=128`
  }
  return null
}

export function ServerListPage() {
  const navigate = useNavigate()
  const { user } = useAuth()
  const { data: servers, isLoading, error, refetch } = useServers()

  if (isLoading) return <LoadingScreen />

  return (
    <div className="min-h-screen bg-gray-900">
      <header className="flex items-center justify-between border-b border-gray-800 px-6 py-4">
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-indigo-600">
            <Bot className="h-4 w-4 text-white" />
          </div>
          <span className="text-lg font-semibold text-white">AkizaCore</span>
        </div>
        <UserMenu />
      </header>

      <main className="mx-auto max-w-4xl px-6 py-10">
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-white">
            Halo, {user?.global_name ?? user?.username ?? 'User'}!
          </h1>
          <p className="mt-1 text-sm text-gray-400">
            Pilih server yang ingin kamu kelola.
          </p>
        </div>

        {error && (
          <ErrorAlert message="Gagal memuat daftar server." onRetry={() => void refetch()} />
        )}

        <div className="grid gap-3">
          {servers?.map((server) => (
            <button
              key={server.id}
              onClick={() => navigate(`/servers/${server.id}/overview`)}
              disabled={!server.bot_active}
              className="flex items-center gap-4 rounded-xl border border-gray-800 bg-gray-900/50 p-4 text-left transition-all hover:border-gray-700 hover:bg-gray-800/50 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {serverIcon(server) ? (
                <img
                  src={serverIcon(server)!}
                  alt={server.name}
                  className="h-12 w-12 rounded-full"
                />
              ) : (
                <div className="flex h-12 w-12 items-center justify-center rounded-full bg-gray-700 text-lg font-bold text-gray-300">
                  {server.name[0]}
                </div>
              )}
              <div className="flex-1">
                <p className="font-medium text-white">{server.name}</p>
                <p className="text-xs text-gray-500">
                  {server.bot_active ? 'Bot aktif' : 'Bot tidak ada di server ini'}
                </p>
              </div>
              {server.bot_active && <ArrowRight className="h-5 w-5 text-gray-500" />}
            </button>
          ))}

          {servers?.length === 0 && (
            <div className="py-16 text-center">
              <p className="text-gray-400">Tidak ada server yang bisa dikelola.</p>
              <p className="mt-1 text-sm text-gray-500">
                Kamu butuh izin Manage Server dan bot harus ada di server tersebut.
              </p>
            </div>
          )}
        </div>
      </main>
    </div>
  )
}
