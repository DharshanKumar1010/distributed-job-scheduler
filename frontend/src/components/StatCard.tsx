interface StatCardProps {
  label: string
  value: string | number
  accentColor?: string
}

export function StatCard({ label, value, accentColor }: StatCardProps) {
  return (
    <div className="rounded-lg border border-border bg-card p-5">
      <div className="text-xs uppercase tracking-widest text-secondary">{label}</div>
      <div
        className="mt-2 font-display text-[2rem] leading-none text-primary"
        style={accentColor ? { color: accentColor } : undefined}
      >
        {value}
      </div>
    </div>
  )
}
