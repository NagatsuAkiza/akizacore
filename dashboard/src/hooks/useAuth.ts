import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api, ApiError } from '../lib/api'
import type { User } from '../types'

export function useAuth() {
  const queryClient = useQueryClient()

  const { data: user, isLoading, error } = useQuery<User>({
    queryKey: ['auth', 'me'],
    queryFn: () => api.get<User>('/auth/me'),
    retry: false,
    staleTime: 5 * 60_000,
  })

  const isAuthenticated = !!user && !error
  const isUnauthenticated = error instanceof ApiError && error.status === 401

  const logout = async () => {
    await api.post('/auth/logout')
    queryClient.clear()
    window.location.href = '/login'
  }

  return { user, isLoading, isAuthenticated, isUnauthenticated, logout }
}
