import { NavLink, useParams } from 'react-router'
import {
  LayoutDashboard,
  Settings,
  Coins,
  Shield,
  Bot,
  ArrowLeft,
} from 'lucide-react'
import { clsx } from 'clsx'

const navItems = [
  { to: 'overview', label: 'Overview', icon: LayoutDashboard },
  { to: 'settings', label: 'Settings', icon: Settings },
  { to: 'economy', label: 'Economy', icon: Coins },
  { to: 'moderation', label: 'Moderation', icon: Shield },
  { to: 'ai', label: 'AI Usage', icon: Bot },
]

export function Sidebar() {
  const { serverId } = useParams<{ serverId: string }>()

  return (
    <aside className="flex h-screen w-64 flex-col border-r border-gray-800 bg-gray-950">
      <div className="flex items-center gap-2 border-b border-gray-800 px-4 py-4">
        <div className="h-8 w-8 rounded-full bg-indigo-600 flex items-center justify-center text-sm font-bold">
          A
        </div>
        <span className="font-semibold text-white">AkizaCore</span>
      </div>

      <nav className="flex-1 space-y-1 px-3 py-4">
        {navItems.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={`/servers/${serverId}/${to}`}
            className={({ isActive }) =>
              clsx(
                'flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors',
                isActive
                  ? 'bg-indigo-600/20 text-indigo-400'
                  : 'text-gray-400 hover:bg-gray-800 hover:text-gray-200',
              )
            }
          >
            <Icon className="h-5 w-5" />
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="border-t border-gray-800 p-3">
        <NavLink
          to="/servers"
          className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-gray-400 hover:bg-gray-800 hover:text-gray-200 transition-colors"
        >
          <ArrowLeft className="h-5 w-5" />
          Semua Server
        </NavLink>
      </div>
    </aside>
  )
}
