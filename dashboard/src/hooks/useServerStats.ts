import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import type { ServerStats } from '../types'

export function useServerStats(serverId: string) {
  return useQuery<ServerStats>({
    queryKey: ['servers', serverId, 'stats'],
    queryFn: () => api.get<ServerStats>(`/servers/${serverId}/stats`),
    enabled: !!serverId,
  })
}
