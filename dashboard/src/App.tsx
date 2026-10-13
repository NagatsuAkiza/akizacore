import { Routes, Route, Navigate } from 'react-router'
import { AuthGuard } from './components/AuthGuard'
import { DashboardLayout } from './layouts/DashboardLayout'
import { LoginPage } from './pages/LoginPage'
import { CallbackPage } from './pages/CallbackPage'
import { ServerListPage } from './pages/ServerListPage'
import { OverviewPage } from './pages/OverviewPage'
import { SettingsPage } from './pages/SettingsPage'
import { EconomyPage } from './pages/EconomyPage'
import { ModerationPage } from './pages/ModerationPage'

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/callback" element={<CallbackPage />} />

      <Route element={<AuthGuard />}>
        <Route path="/servers" element={<ServerListPage />} />
        <Route path="/servers/:serverId" element={<DashboardLayout />}>
          <Route index element={<Navigate to="overview" replace />} />
          <Route path="overview" element={<OverviewPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="economy" element={<EconomyPage />} />
          <Route path="moderation" element={<ModerationPage />} />
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/servers" replace />} />
    </Routes>
  )
}
