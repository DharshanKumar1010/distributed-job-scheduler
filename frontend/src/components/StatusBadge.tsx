type BadgeVariant = 'success' | 'warning' | 'danger' | 'neutral'

const STATUS_VARIANTS: Record<string, BadgeVariant> = {
  completed: 'success',
  active: 'success',
  connected: 'success',
  running: 'warning',
  claimed: 'warning',
  busy: 'warning',
  pending: 'warning',
  paused: 'warning',
  scheduled: 'neutral',
  queued: 'neutral',
  blocked: 'neutral',
  idle: 'neutral',
  cancelled: 'neutral',
  resolved: 'neutral',
  failed: 'danger',
  dead: 'danger',
  offline: 'danger',
  unresolved: 'danger',
}

const VARIANT_STYLES: Record<BadgeVariant, { bg: string; text: string }> = {
  success: { bg: 'rgba(16, 185, 129, 0.15)', text: '#10B981' },
  warning: { bg: 'rgba(245, 158, 11, 0.15)', text: '#F59E0B' },
  danger: { bg: 'rgba(239, 68, 68, 0.15)', text: '#EF4444' },
  neutral: { bg: 'rgba(100, 116, 139, 0.15)', text: '#94A3B8' },
}

interface StatusBadgeProps {
  status: string
  label?: string
}

export function StatusBadge({ status, label }: StatusBadgeProps) {
  const variant = STATUS_VARIANTS[status] ?? 'neutral'
  const style = VARIANT_STYLES[variant]

  return (
    <span
      className="inline-flex items-center whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium capitalize"
      style={{ backgroundColor: style.bg, color: style.text }}
    >
      {label ?? status}
    </span>
  )
}
