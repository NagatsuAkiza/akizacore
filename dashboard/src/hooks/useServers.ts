import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import type { Server } from '../types'

export function useServers() {
  return useQuery<Server[]>({
    queryKey: ['servers'],
    queryFn: () => api.get<Server[]>('/servers'),
  })
}
