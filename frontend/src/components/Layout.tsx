import { LayoutDashboard, ListTree, LogOut, Skull, Users } from 'lucide-react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useWebSocket } from '../hooks/useWebSocket'
import { useAuthStore } from '../store/authStore'
import { Logo } from './Logo'
import { PulseRing } from './PulseRing'
import { ToastContainer } from './Toast'

function DagIcon({ size = 16, strokeWidth = 1.75 }: { size?: number; strokeWidth?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke="currentColor">
      <circle cx="3.5" cy="3.5" r="2" strokeWidth={strokeWidth} />
      <circle cx="12.5" cy="3.5" r="2" strokeWidth={strokeWidth} />
      <circle cx="8" cy="12.5" r="2" strokeWidth={strokeWidth} />
      <path d="M5 4.8 L6.5 10.8" strokeWidth={strokeWidth} strokeLinecap="round" />
      <path d="M11 4.8 L9.5 10.8" strokeWidth={strokeWidth} strokeLinecap="round" />
    </svg>
  )
}

function GearIcon({ size = 16, strokeWidth = 1.75 }: { size?: number; strokeWidth?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke="currentColor">
      <circle cx="8" cy="8" r="2.25" strokeWidth={strokeWidth} />
      <path
        d="M8 1.8v1.6M8 12.6v1.6M14.2 8h-1.6M3.4 8H1.8M12.1 3.9l-1.13 1.13M5.03 10.97 3.9 12.1M12.1 12.1l-1.13-1.13M5.03 5.03 3.9 3.9"
        strokeWidth={strokeWidth}
        strokeLinecap="round"
      />
    </svg>
  )
}

const NAV_ITEMS = [
  { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/queues', label: 'Queues', icon: ListTree },
  { to: '/workers', label: 'Workers', icon: Users },
  { to: '/workflows', label: 'Workflows', icon: DagIcon },
  { to: '/dlq', label: 'Dead Letters', icon: Skull },
]

function breadcrumbFor(pathname: string): string {
  if (pathname.startsWith('/dashboard')) return 'Dashboard'
  if (/^\/queues\/[^/]+/.test(pathname)) return 'Queues / Queue Detail'
  if (pathname.startsWith('/queues')) return 'Queues'
  if (/^\/jobs\/[^/]+/.test(pathname)) return 'Jobs / Job Detail'
  if (pathname.startsWith('/workers')) return 'Workers'
  if (pathname.startsWith('/workflows')) return 'Workflows'
  if (pathname.startsWith('/dlq')) return 'Dead Letter Queue'
  if (pathname.startsWith('/settings')) return 'Settings'
  return ''
}

const CONNECTION_DISPLAY: Record<
  ReturnType<typeof useWebSocket>['status'],
  { color: 'success' | 'warning' | 'danger'; pulse: boolean; label: string; textColor: string }
> = {
  connected: { color: 'success', pulse: true, label: 'Live', textColor: 'var(--success)' },
  connecting: { color: 'warning', pulse: true, label: 'Connecting...', textColor: 'var(--warning)' },
  reconnecting: { color: 'warning', pulse: false, label: 'Reconnecting...', textColor: 'var(--warning)' },
  disconnected: { color: 'danger', pulse: false, label: 'Offline', textColor: 'var(--danger)' },
}

const MAX_RECONNECT_DISPLAY = 6

export function Layout() {
  const { status: wsStatus, reconnectAttempt } = useWebSocket()
  const location = useLocation()
  const navigate = useNavigate()
  const user = useAuthStore((s) => s.user)
  const logout = useAuthStore((s) => s.logout)

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  const connection = CONNECTION_DISPLAY[wsStatus]
  const connectionLabel =
    wsStatus === 'reconnecting'
      ? `Reconnecting (${Math.min(reconnectAttempt, MAX_RECONNECT_DISPLAY)}/${MAX_RECONNECT_DISPLAY})...`
      : connection.label

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

        <div className="border-t border-border px-3 py-3">
          <NavLink
            to="/settings"
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
            <GearIcon size={16} strokeWidth={1.75} />
            Settings
          </NavLink>
        </div>

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
            <PulseRing color={connection.color} pulse={connection.pulse} />
            <span className="text-xs" style={{ color: connection.textColor }}>
              {connectionLabel}
            </span>
          </div>
        </header>

        <main className="flex-1 overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>

      <ToastContainer />
    </div>
  )
}
