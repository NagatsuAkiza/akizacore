import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../lib/api'
import type { ServerSettings } from '../types'

export function useServerSettings(serverId: string) {
  const queryClient = useQueryClient()

  const query = useQuery<ServerSettings>({
    queryKey: ['servers', serverId, 'settings'],
    queryFn: () => api.get<ServerSettings>(`/servers/${serverId}/settings`),
    enabled: !!serverId,
  })

  const mutation = useMutation({
    mutationFn: (settings: Partial<ServerSettings>) =>
      api.put<ServerSettings>(`/servers/${serverId}/settings`, settings),
    onSuccess: (data) => {
      queryClient.setQueryData(['servers', serverId, 'settings'], data)
    },
  })

  return { ...query, updateSettings: mutation.mutateAsync, isUpdating: mutation.isPending }
}
