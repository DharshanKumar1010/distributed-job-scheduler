interface SkeletonProps {
  rows?: number
  className?: string
}

export function Skeleton({ rows = 3, className = '' }: SkeletonProps) {
  return (
    <div className={`space-y-3 ${className}`}>
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          className="h-4 animate-pulse rounded bg-elevated"
          style={{ width: i === rows - 1 ? '60%' : '100%' }}
        />
      ))}
    </div>
  )
}
