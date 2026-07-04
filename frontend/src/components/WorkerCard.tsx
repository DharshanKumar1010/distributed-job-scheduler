import { useWorker } from '../hooks/useWorkers'
import { formatRelativeAge, truncateId } from '../lib/format'
import type { Worker } from '../types'
import { PulseRing, type PulseColor } from './PulseRing'

const STATUS_PULSE: Record<Worker['status'], { color: PulseColor; pulse: boolean }> = {
  idle: { color: 'success', pulse: true },
  busy: { color: 'warning', pulse: true },
  offline: { color: 'danger', pulse: false },
}

function ProgressBar({ value }: { value: number }) {
  return (
    <div className="h-1 w-full overflow-hidden rounded-full bg-elevated">
      <div
        className="h-full rounded-full bg-accent transition-all"
        style={{ width: `${Math.min(100, Math.max(0, value))}%` }}
      />
    </div>
  )
}

interface WorkerCardProps {
  worker: Worker
  queueName?: string
}

export function WorkerCard({ worker, queueName }: WorkerCardProps) {
  const { data: detail } = useWorker(worker.id)
  const current = detail ?? worker
  const latestHeartbeat = detail?.heartbeats?.[0]
  const { color, pulse } = STATUS_PULSE[current.status]

  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate font-display text-sm text-primary">{current.hostname}</div>
          <div className="font-mono text-xs text-mono">{truncateId(current.id)}</div>
        </div>
        <PulseRing color={color} pulse={pulse} />
      </div>

      {queueName && (
        <span className="mt-3 inline-flex rounded-full border border-border bg-elevated px-2 py-0.5 text-xs text-secondary">
          {queueName}
        </span>
      )}

      <div className="mt-4 space-y-2">
        <div>
          <div className="mb-1 flex justify-between text-xs text-secondary">
            <span>CPU</span>
            <span>
              {latestHeartbeat?.cpu_pct != null ? `${latestHeartbeat.cpu_pct.toFixed(0)}%` : '—'}
            </span>
          </div>
          <ProgressBar value={latestHeartbeat?.cpu_pct ?? 0} />
        </div>
        <div>
          <div className="mb-1 flex justify-between text-xs text-secondary">
            <span>Mem</span>
            <span>
              {latestHeartbeat?.mem_pct != null ? `${latestHeartbeat.mem_pct.toFixed(0)}%` : '—'}
            </span>
          </div>
          <ProgressBar value={latestHeartbeat?.mem_pct ?? 0} />
        </div>
      </div>

      <div className="mt-4 text-sm text-secondary">
        {current.current_jobs} active job{current.current_jobs === 1 ? '' : 's'}
      </div>
      <div className="mt-1 font-mono text-xs text-mono">
        {current.last_seen ? `seen ${formatRelativeAge(current.last_seen)}` : 'never seen'}
      </div>
    </div>
  )
}
