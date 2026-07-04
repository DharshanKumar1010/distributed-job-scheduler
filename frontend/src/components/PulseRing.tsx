export type PulseColor = 'success' | 'warning' | 'danger'

interface PulseRingProps {
  color: PulseColor
  /** Static dot with no animation — used for "dead"/offline states. */
  pulse?: boolean
  className?: string
}

const COLOR_VAR: Record<PulseColor, string> = {
  success: 'var(--success)',
  warning: 'var(--warning)',
  danger: 'var(--danger)',
}

export function PulseRing({ color, pulse = true, className = '' }: PulseRingProps) {
  const dotColor = COLOR_VAR[color]

  return (
    <span className={`relative inline-flex h-2.5 w-2.5 shrink-0 ${className}`}>
      {pulse && (
        <span
          className="absolute inline-flex h-full w-full animate-pulse-ring rounded-full"
          style={{ backgroundColor: dotColor }}
        />
      )}
      <span
        className="relative inline-flex h-2.5 w-2.5 rounded-full"
        style={{ backgroundColor: dotColor }}
      />
    </span>
  )
}
