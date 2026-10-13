import { useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router'
import { LoadingScreen } from '../components/LoadingScreen'

export function CallbackPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()

  useEffect(() => {
    const error = searchParams.get('error')
    if (error) {
      navigate('/login', { replace: true })
      return
    }
    // Backend handles the callback and sets the session cookie.
    // After the backend redirects here, we simply go to the server list.
    navigate('/servers', { replace: true })
  }, [navigate, searchParams])

  return <LoadingScreen />
}
