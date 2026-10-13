import { Navigate, Outlet } from 'react-router'
import { useAuth } from '../hooks/useAuth'
import { LoadingScreen } from './LoadingScreen'

export function AuthGuard() {
  const { isLoading, isAuthenticated, isUnauthenticated } = useAuth()

  if (isLoading) return <LoadingScreen />
  if (isUnauthenticated) return <Navigate to="/login" replace />
  if (!isAuthenticated) return <LoadingScreen />

  return <Outlet />
}
