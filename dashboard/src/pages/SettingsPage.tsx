import { useState, useEffect } from 'react'
import { useParams } from 'react-router'
import { Save, Loader2 } from 'lucide-react'
import { useServerSettings } from '../hooks/useServerSettings'
import { PageHeader } from '../components/PageHeader'
import { ErrorAlert } from '../components/ErrorAlert'

export function SettingsPage() {
  const { serverId } = useParams<{ serverId: string }>()
  const { data: settings, isLoading, error, refetch, updateSettings, isUpdating } =
    useServerSettings(serverId!)

  const [prefix, setPrefix] = useState('')
  const [logChannelId, setLogChannelId] = useState('')
  const [welcomeChannelId, setWelcomeChannelId] = useState('')
  const [welcomeMessage, setWelcomeMessage] = useState('')
  const [features, setFeatures] = useState<Record<string, boolean>>({})

  useEffect(() => {
    if (settings) {
      setPrefix(settings.prefix)
      setLogChannelId(settings.log_channel_id ?? '')
      setWelcomeChannelId(settings.welcome_channel_id ?? '')
      setWelcomeMessage(settings.welcome_message ?? '')
      setFeatures(settings.features)
    }
  }, [settings])

  const handleSave = async () => {
    await updateSettings({
      prefix,
      log_channel_id: logChannelId || null,
      welcome_channel_id: welcomeChannelId || null,
      welcome_message: welcomeMessage || null,
      features,
    })
  }

  const toggleFeature = (key: string) => {
    setFeatures((prev) => ({ ...prev, [key]: !prev[key] }))
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-500" />
      </div>
    )
  }

  if (error) {
    return <ErrorAlert message="Gagal memuat settings." onRetry={() => void refetch()} />
  }

  return (
    <div className="space-y-6">
      <PageHeader title="Settings" description="Konfigurasi server.">
        <button
          onClick={() => void handleSave()}
          disabled={isUpdating}
          className="flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500 disabled:opacity-50"
        >
          {isUpdating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
          Simpan
        </button>
      </PageHeader>

      <div className="space-y-6">
        {/* General */}
        <section className="rounded-xl border border-gray-800 bg-gray-900/50 p-6">
          <h2 className="mb-4 text-lg font-semibold text-white">Umum</h2>
          <div className="space-y-4">
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-300">Prefix</label>
              <input
                value={prefix}
                onChange={(e) => setPrefix(e.target.value)}
                className="w-full max-w-xs rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-indigo-500 focus:outline-none"
                placeholder="!"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-300">Log Channel ID</label>
              <input
                value={logChannelId}
                onChange={(e) => setLogChannelId(e.target.value)}
                className="w-full max-w-xs rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-indigo-500 focus:outline-none"
                placeholder="Kosongkan jika tidak ada"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-300">Welcome Channel ID</label>
              <input
                value={welcomeChannelId}
                onChange={(e) => setWelcomeChannelId(e.target.value)}
                className="w-full max-w-xs rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-indigo-500 focus:outline-none"
                placeholder="Kosongkan jika tidak ada"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-300">Welcome Message</label>
              <textarea
                value={welcomeMessage}
                onChange={(e) => setWelcomeMessage(e.target.value)}
                rows={3}
                className="w-full rounded-lg border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white placeholder-gray-500 focus:border-indigo-500 focus:outline-none"
                placeholder="Pesan selamat datang..."
              />
            </div>
          </div>
        </section>

        {/* Features */}
        <section className="rounded-xl border border-gray-800 bg-gray-900/50 p-6">
          <h2 className="mb-4 text-lg font-semibold text-white">Fitur</h2>
          <div className="space-y-3">
            {Object.entries(features).map(([key, enabled]) => (
              <div key={key} className="flex items-center justify-between">
                <span className="text-sm font-medium capitalize text-gray-300">{key}</span>
                <button
                  onClick={() => toggleFeature(key)}
                  className={`relative h-6 w-11 rounded-full transition-colors ${
                    enabled ? 'bg-indigo-600' : 'bg-gray-700'
                  }`}
                >
                  <span
                    className={`absolute left-0.5 top-0.5 h-5 w-5 rounded-full bg-white transition-transform ${
                      enabled ? 'translate-x-5' : 'translate-x-0'
                    }`}
                  />
                </button>
              </div>
            ))}
            {Object.keys(features).length === 0 && (
              <p className="text-sm text-gray-500">Tidak ada fitur yang dikonfigurasi.</p>
            )}
          </div>
        </section>
      </div>
    </div>
  )
}
