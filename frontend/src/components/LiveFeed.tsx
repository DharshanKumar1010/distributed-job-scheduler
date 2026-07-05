import { useEffect, useMemo, useRef, useState } from 'react'
import { useWebSocket } from '../hooks/useWebSocket'
import { truncateId } from '../lib/format'
import type {
  WsEnvelope,
  WsEventName,
  WsJobEventData,
  WsWorkerHeartbeatData,
} from '../types'

const HEARTBEAT_THROTTLE_MS = 30_000
const MAX_VISIBLE = 30

const EVENT_STYLES: Record<WsEventName, { bg: string; text: string; label: string }> = {
  'connection.established': { bg: 'rgba(16, 185, 129, 0.15)', text: '#10B981', label: 'connected' },
  snapshot: { bg: 'rgba(59, 130, 246, 0.15)', text: '#3B82F6', label: 'sync' },
  'job.created': { bg: 'rgba(59, 130, 246, 0.15)', text: '#3B82F6', label: 'created' },
  'job.claimed': { bg: 'rgba(59, 130, 246, 0.15)', text: '#3B82F6', label: 'claimed' },
  'job.running': { bg: 'rgba(245, 158, 11, 0.15)', text: '#F59E0B', label: 'running' },
  'job.updated': { bg: 'rgba(100, 116, 139, 0.15)', text: '#94A3B8', label: 'updated' },
  'job.completed': { bg: 'rgba(16, 185, 129, 0.15)', text: '#10B981', label: 'completed' },
  'job.failed': { bg: 'rgba(239, 68, 68, 0.15)', text: '#EF4444', label: 'failed' },
  'job.dead': { bg: 'rgba(127, 29, 29, 0.35)', text: '#F87171', label: 'dead' },
  'job.unblocked': { bg: 'rgba(59, 130, 246, 0.15)', text: '#3B82F6', label: 'unblocked' },
  'worker.connected': { bg: 'rgba(16, 185, 129, 0.15)', text: '#10B981', label: 'worker' },
  'worker.disconnected': { bg: 'rgba(100, 116, 139, 0.15)', text: '#94A3B8', label: 'worker' },
  'worker.heartbeat': { bg: 'rgba(100, 116, 139, 0.15)', text: '#94A3B8', label: 'heartbeat' },
  'queue.stats': { bg: 'rgba(100, 116, 139, 0.15)', text: '#94A3B8', label: 'stats' },
  'queue.rate_limited': { bg: 'rgba(245, 158, 11, 0.15)', text: '#F59E0B', label: 'rate limited' },
}

/** Worker heartbeats fire every ~10s; only surface one per worker per 30s so
 * the feed isn't dominated by them. Processes newest-first (as stored). */
function throttleHeartbeats(events: WsEnvelope[]): WsEnvelope[] {
  const lastShownByWorker = new Map<string, number>()
  const result: WsEnvelope[] = []

  for (const envelope of events) {
    if (envelope.event !== 'worker.heartbeat') {
      result.push(envelope)
      continue
    }
    const workerId = (envelope.data as WsWorkerHeartbeatData | undefined)?.worker_id
    if (!workerId) {
      result.push(envelope)
      continue
    }
    const ts = new Date(envelope.ts).getTime()
    const lastShown = lastShownByWorker.get(workerId)
    if (lastShown === undefined || lastShown - ts >= HEARTBEAT_THROTTLE_MS) {
      lastShownByWorker.set(workerId, ts)
      result.push(envelope)
    }
  }

  return result
}

function describeEvent(envelope: WsEnvelope): string {
  const { event, data } = envelope

  switch (event) {
    case 'job.claimed': {
      const p = data as WsJobEventData
      return `${p.name} claimed (attempt ${p.attempts})`
    }
    case 'job.running': {
      const p = data as WsJobEventData
      return `${p.name} is now running on worker-${truncateId(p.worker_id ?? '', 8)}`
    }
    case 'job.completed': {
      const p = data as WsJobEventData
      const seconds = p.duration_ms != null ? (p.duration_ms / 1000).toFixed(1) : '?'
      return `${p.name} completed in ${seconds}s`
    }
    case 'job.failed': {
      const p = data as WsJobEventData
      if (p.will_retry && p.next_retry_at) {
        const retrySeconds = Math.max(
          0,
          Math.round((new Date(p.next_retry_at).getTime() - Date.now()) / 1000),
        )
        return `${p.name} failed — retrying in ${retrySeconds}s (attempt ${p.attempts}/${p.max_attempts})`
      }
      return `${p.name} failed`
    }
    case 'job.dead': {
      const p = data as WsJobEventData
      return `${p.name} exhausted all retries and moved to the dead letter queue`
    }
    case 'worker.heartbeat': {
      const p = data as WsWorkerHeartbeatData
      return `Worker ${truncateId(p.worker_id, 8)} heartbeat`
    }
    case 'worker.connected':
      return 'Worker connected'
    case 'worker.disconnected':
      return 'Worker disconnected'
    case 'queue.stats':
      return 'Queue stats updated'
    case 'snapshot':
      return 'Connected — synced current state'
    case 'connection.established':
      return 'Connection established'
    default:
      return event
  }
}

function LiveTimestamp({ ts }: { ts: string }) {
  const [, setTick] = useState(0)
  useEffect(() => {
    const interval = setInterval(() => setTick((t) => t + 1), 1000)
    return () => clearInterval(interval)
  }, [])
  const seconds = Math.max(0, Math.round((Date.now() - new Date(ts).getTime()) / 1000))
  return <span className="shrink-0 font-mono text-xs text-secondary">{seconds}s ago</span>
}

function LiveFeedRow({ envelope, isNew }: { envelope: WsEnvelope; isNew: boolean }) {
  const [entered, setEntered] = useState(!isNew)
  useEffect(() => {
    if (!isNew) return undefined
    const raf = requestAnimationFrame(() => setEntered(true))
    return () => cancelAnimationFrame(raf)
  }, [isNew])

  const style = EVENT_STYLES[envelope.event] ?? EVENT_STYLES['queue.stats']

  return (
    <div
      className={`flex items-center gap-3 border-t border-border py-2.5 transition-all duration-200 ease-out first:border-t-0 ${
        entered ? 'translate-y-0 opacity-100' : '-translate-y-2 opacity-0'
      }`}
    >
      <span
        className="inline-flex shrink-0 items-center whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium"
        style={{ backgroundColor: style.bg, color: style.text }}
      >
        {style.label}
      </span>
      <span className="min-w-0 flex-1 truncate text-sm text-primary">{describeEvent(envelope)}</span>
      <LiveTimestamp ts={envelope.ts} />
    </div>
  )
}

export function LiveFeed() {
  const { eventHistory } = useWebSocket()
  const seenKeysRef = useRef(new Set<string>())

  const displayed = useMemo(() => {
    const throttled = throttleHeartbeats(eventHistory).slice(0, MAX_VISIBLE)
    return throttled.map((envelope, index) => ({
      envelope,
      key: `${envelope.ts}-${envelope.event}-${index}`,
    }))
  }, [eventHistory])

  if (displayed.length === 0) {
    return <p className="py-6 text-center text-sm text-secondary">No recent activity</p>
  }

  return (
    <div className={displayed.length >= MAX_VISIBLE ? 'max-h-[600px] overflow-y-auto' : ''}>
      {displayed.map(({ envelope, key }) => {
        const isNew = !seenKeysRef.current.has(key)
        seenKeysRef.current.add(key)
        return <LiveFeedRow key={key} envelope={envelope} isNew={isNew} />
      })}
    </div>
  )
}
