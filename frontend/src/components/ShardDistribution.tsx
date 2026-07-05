import { useShardDistribution } from '../hooks/useShards'
import { PulseRing } from './PulseRing'
import { Skeleton } from './Skeleton'

function truncate(name: string, max = 12): string {
  return name.length > max ? `${name.slice(0, max - 1)}…` : name
}

interface ShardDistributionProps {
  queueId: string
}

export function ShardDistribution({ queueId }: ShardDistributionProps) {
  const { data: distribution, isLoading } = useShardDistribution(queueId)

  if (isLoading || !distribution) {
    return (
      <div className="rounded-lg border border-border bg-card p-5">
        <Skeleton rows={3} />
      </div>
    )
  }

  const totalPending = distribution.shards.reduce((sum, s) => sum + s.pending_jobs, 0)

  const offenders = distribution.shards.filter((s) => s.workers.length === 0 && s.pending_jobs > 0)
  const worstOffender = offenders.sort((a, b) => b.pending_jobs - a.pending_jobs)[0]

  return (
    <div>
      <div className="flex flex-wrap gap-3">
        {distribution.shards.map((s) => {
          const pendingRatio = totalPending > 0 ? s.pending_jobs / totalPending : 0
          return (
            <div
              key={s.shard_id}
              className="w-[140px] shrink-0 rounded-lg border border-border bg-card p-3"
            >
              <div className="mb-2 font-mono text-xs text-secondary">Shard {s.shard_id}</div>

              <div className="mb-3 flex min-h-[46px] flex-wrap gap-2">
                {s.workers.length === 0 ? (
                  <div className="text-xs text-secondary">No workers</div>
                ) : (
                  s.workers.map((w) => (
                    <div key={w.worker_id} className="flex flex-col items-center gap-1">
                      <PulseRing color="success" pulse size={8} />
                      <div className="font-mono text-[10px] text-secondary">
                        {truncate(w.hostname)}
                      </div>
                    </div>
                  ))
                )}
              </div>

              <div className="mb-1 h-1 w-full overflow-hidden rounded-full bg-elevated">
                <div
                  className="h-full rounded-full bg-accent transition-all duration-300 ease-in-out"
                  style={{ width: `${Math.min(100, pendingRatio * 100)}%` }}
                />
              </div>
              <div className="text-xs text-secondary">{s.pending_jobs} pending</div>
              {s.running_jobs > 0 && (
                <div className="mt-0.5 text-xs" style={{ color: 'var(--warning)' }}>
                  {s.running_jobs} running
                </div>
              )}
            </div>
          )
        })}
      </div>

      {distribution.recommendation === 'add_workers' && worstOffender && (
        <div
          className="mt-4 rounded-md border-l-4 bg-elevated px-4 py-3 text-sm text-primary"
          style={{ borderLeftColor: 'var(--warning)' }}
        >
          ⚠ Shard {worstOffender.shard_id} has {worstOffender.pending_jobs} pending jobs but no
          active workers. Start another worker with SHARD_ID={worstOffender.shard_id} to process
          them.
        </div>
      )}

      {distribution.recommendation === 'reduce_shards' && (
        <div
          className="mt-4 rounded-md border-l-4 bg-elevated px-4 py-3 text-sm text-primary"
          style={{ borderLeftColor: 'var(--accent)' }}
        >
          ℹ You have {distribution.shard_count} shards but only{' '}
          {new Set(distribution.shards.flatMap((s) => s.workers.map((w) => w.worker_id))).size}{' '}
          workers. Consider reducing shard_count for better distribution.
        </div>
      )}
    </div>
  )
}
