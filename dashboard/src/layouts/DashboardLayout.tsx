import { Outlet } from 'react-router'
import { Sidebar } from '../components/Sidebar'
import { UserMenu } from '../components/UserMenu'

export function DashboardLayout() {
  return (
    <div className="flex h-screen">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <header className="flex items-center justify-end border-b border-gray-800 bg-gray-950 px-6 py-3">
          <UserMenu />
        </header>
        <main className="flex-1 overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
