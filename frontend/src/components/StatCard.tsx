interface StatCardProps {
  label: string
  value: string | number
}

export function StatCard({ label, value }: StatCardProps) {
  return (
    <div className="rounded-lg border border-border bg-card p-5">
      <div className="text-xs uppercase tracking-widest text-secondary">{label}</div>
      <div className="mt-2 font-display text-[2rem] leading-none text-primary">{value}</div>
    </div>
  )
}
