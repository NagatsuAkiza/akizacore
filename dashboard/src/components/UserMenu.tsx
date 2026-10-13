import { useState, useRef, useEffect } from 'react'
import { LogOut, ChevronDown } from 'lucide-react'
import { useAuth } from '../hooks/useAuth'

function discordAvatar(user: { id: string; avatar: string | null; discriminator: string }) {
  if (user.avatar) {
    return `https://cdn.discordapp.com/avatars/${user.id}/${user.avatar}.webp?size=64`
  }
  const index =
    user.discriminator === '0'
      ? (BigInt(user.id) >> 22n) % 6n
      : Number(user.discriminator) % 5
  return `https://cdn.discordapp.com/embed/avatars/${index}.png`
}

export function UserMenu() {
  const { user, logout } = useAuth()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  if (!user) return null

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 rounded-lg px-3 py-1.5 hover:bg-gray-800 transition-colors"
      >
        <img
          src={discordAvatar(user)}
          alt={user.username}
          className="h-7 w-7 rounded-full"
        />
        <span className="text-sm font-medium text-gray-200">
          {user.global_name ?? user.username}
        </span>
        <ChevronDown className="h-4 w-4 text-gray-400" />
      </button>

      {open && (
        <div className="absolute right-0 mt-2 w-48 rounded-lg border border-gray-700 bg-gray-800 py-1 shadow-xl z-50">
          <button
            onClick={() => {
              setOpen(false)
              void logout()
            }}
            className="flex w-full items-center gap-2 px-4 py-2 text-sm text-red-400 hover:bg-gray-700 transition-colors"
          >
            <LogOut className="h-4 w-4" />
            Logout
          </button>
        </div>
      )}
    </div>
  )
}
