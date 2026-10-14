import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import type { ServerUsageReport } from '../types/aiUsage'

export function useAiUsage(serverId: string, days: number) {
  return useQuery<ServerUsageReport>({
    queryKey: ['servers', serverId, 'ai', 'usage', days],
    queryFn: () => api.get<ServerUsageReport>(`/servers/${serverId}/ai/usage?days=${days}`),
    enabled: !!serverId,
  })
}