export function HexagonLogo({ size = 20 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path
        d="M10 1L18 5.5V14.5L10 19L2 14.5V5.5L10 1Z"
        stroke="var(--accent)"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export function Logo({ size = 20 }: { size?: number }) {
  return (
    <div className="flex items-center gap-2">
      <HexagonLogo size={size} />
      <span className="font-display text-sm text-primary">Scheduler</span>
    </div>
  )
}
