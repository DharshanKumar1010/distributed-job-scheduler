import { LayoutDashboard, ListTree, LogOut, Skull, Users } from 'lucide-react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useWebSocket } from '../hooks/useWebSocket'
import { useAuthStore } from '../store/authStore'
import { useLiveStore } from '../store/liveStore'
import { Logo } from './Logo'
import { PulseRing } from './PulseRing'

const NAV_ITEMS = [
  { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/queues', label: 'Queues', icon: ListTree },
  { to: '/workers', label: 'Workers', icon: Users },
  { to: '/dlq', label: 'Dead Letters', icon: Skull },
]

function breadcrumbFor(pathname: string): string {
  if (pathname.startsWith('/dashboard')) return 'Dashboard'
  if (/^\/queues\/[^/]+/.test(pathname)) return 'Queues / Queue Detail'
  if (pathname.startsWith('/queues')) return 'Queues'
  if (/^\/jobs\/[^/]+/.test(pathname)) return 'Jobs / Job Detail'
  if (pathname.startsWith('/workers')) return 'Workers'
  if (pathname.startsWith('/dlq')) return 'Dead Letter Queue'
  return ''
}

export function Layout() {
  useWebSocket()
  const location = useLocation()
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  const logout = useAuthStore((s) => s.logout)
  const wsStatus = useLiveStore((s) => s.status)

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  return (
    <div className="flex h-full min-h-screen bg-base">
      <aside className="flex w-[220px] shrink-0 flex-col border-r border-border bg-card">
        <div className="px-5 py-5">
          <Logo />
        </div>

        <nav className="mt-2 flex flex-1 flex-col gap-1 px-3">
          {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `flex items-center gap-2.5 rounded-md border-l-2 px-3 py-2 text-sm transition-colors ${
                  isActive
                    ? 'border-accent text-primary'
                    : 'border-transparent text-secondary hover:text-primary'
                }`
              }
              style={({ isActive }) => ({
                backgroundColor: isActive ? 'var(--accent-glow)' : 'transparent',
              })}
            >
              <Icon size={16} strokeWidth={1.75} />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-border px-4 py-4">
          <div className="truncate text-xs text-secondary">{user?.email}</div>
          <button
            type="button"
            onClick={handleLogout}
            className="mt-2 flex items-center gap-1.5 text-xs text-secondary transition-colors hover:text-primary"
          >
            <LogOut size={14} />
            Log out
          </button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center justify-between border-b border-border px-6">
          <div className="text-sm text-secondary">{breadcrumbFor(location.pathname)}</div>
          <div className="flex items-center gap-2">
            <PulseRing color={wsStatus === 'connected' ? 'success' : 'danger'} pulse={wsStatus === 'connected'} />
            <span className="text-xs text-secondary">
              {wsStatus === 'connected' ? 'Live' : 'Offline'}
            </span>
          </div>
        </header>

        <main className="flex-1 overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
