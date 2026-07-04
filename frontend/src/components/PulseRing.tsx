export type PulseColor = 'success' | 'warning' | 'danger'

interface PulseRingProps {
  color: PulseColor
  /** Static dot with no animation — used for "dead"/offline states. */
  pulse?: boolean
  /** Dot diameter in px (the outer expanding ring scales from this size). */
  size?: number
  className?: string
}

const COLOR_VAR: Record<PulseColor, string> = {
  success: 'var(--success)',
  warning: 'var(--warning)',
  danger: 'var(--danger)',
}

export function PulseRing({ color, pulse = true, size = 10, className = '' }: PulseRingProps) {
  const dotColor = COLOR_VAR[color]

  return (
    <span
      className={`relative inline-flex shrink-0 ${className}`}
      style={{ width: size, height: size }}
    >
      {pulse && (
        <span
          className="absolute inline-flex h-full w-full animate-pulse-ring rounded-full"
          style={{ backgroundColor: dotColor }}
        />
      )}
      <span
        className="relative inline-flex h-full w-full rounded-full"
        style={{ backgroundColor: dotColor }}
      />
    </span>
  )
}
