import { useEffect } from 'react'
import { queryClient } from '../lib/queryClient'
import { useAuthStore } from '../store/authStore'
import { useLiveStatsStore } from '../store/liveStatsStore'
import { useLiveStore } from '../store/liveStore'
import { useToastStore } from '../store/toastStore'
import type {
  JobDetail,
  JobStatus,
  Worker,
  WorkerDetail,
  WorkerHeartbeat,
  WsDlqAiSummaryReadyData,
  WsEnvelope,
  WsJobEventData,
  WsQueueRateLimitedData,
  WsQueueRebalancingData,
  WsQueueStatsData,
  WsWorkerHeartbeatData,
} from '../types'

// Exponential backoff: 1s, 2s, 4s, 8s, 16s, then plateaus at 30s.
const RECONNECT_DELAYS_MS = [1000, 2000, 4000, 8000, 16000, 30000]

function resolveWsUrl(token: string): string {
  const base: string = import.meta.env.VITE_API_BASE_URL
  const wsBase = base.replace(/^http/, 'ws')
  return `${wsBase}/ws/connect?token=${encodeURIComponent(token)}`
}

// ---- Module-level singleton connection state -----------------------------
// Deliberately outside React state: several components may call
// useWebSocket() (Layout for the header dot, DashboardPage for the LIVE
// badge, ...) but must all share exactly one underlying connection.
let socket: WebSocket | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let reconnectAttempt = 0
let intentionalClose = false

function jobStatusFromEvent(event: WsEnvelope['event'], payload: WsJobEventData): JobStatus | null {
  switch (event) {
    case 'job.claimed':
      return 'claimed'
    case 'job.running':
      return 'running'
    case 'job.completed':
      return 'completed'
    case 'job.failed':
      return payload.will_retry ? 'queued' : null
    case 'job.dead':
      return 'dead'
    case 'job.unblocked':
      return 'queued'
    default:
      return null
  }
}

function applyJobEventPatch(
  job: JobDetail,
  event: WsEnvelope['event'],
  payload: WsJobEventData,
): JobDetail {
  const status = jobStatusFromEvent(event, payload)
  const patch: Partial<JobDetail> = {}
  if (status) patch.status = status
  if (payload.worker_id !== undefined) patch.worker_id = payload.worker_id ?? null
  if (payload.started_at) patch.started_at = payload.started_at
  if (payload.error_message !== undefined) patch.error_message = payload.error_message
  if (payload.next_retry_at !== undefined) patch.scheduled_at = payload.next_retry_at
  if (event === 'job.dead' && payload.last_error) patch.error_message = payload.last_error
  return { ...job, ...patch }
}

function handleEnvelope(envelope: WsEnvelope): void {
  useLiveStore.getState().pushEvent(envelope)

  const { event, data, ts } = envelope
  const stats = useLiveStatsStore.getState()

  switch (event) {
    case 'job.claimed':
    case 'job.running':
    case 'job.completed':
    case 'job.failed':
    case 'job.dead': {
      const payload = data as WsJobEventData
      queryClient.setQueryData<JobDetail>(['job', payload.job_id], (old) =>
        old ? applyJobEventPatch(old, event, payload) : old,
      )
      queryClient.invalidateQueries({ queryKey: ['jobs', payload.queue_id] })
      if (event === 'job.completed') stats.incrementCurrentMinuteBucket()
      if (event === 'job.completed' || event === 'job.dead') {
        queryClient.invalidateQueries({ queryKey: ['job-dependents', payload.job_id] })
      }
      break
    }
    case 'job.unblocked': {
      const payload = data as WsJobEventData
      queryClient.setQueryData<JobDetail>(['job', payload.job_id], (old) =>
        old ? applyJobEventPatch(old, event, payload) : old,
      )
      queryClient.invalidateQueries({ queryKey: ['jobs', payload.queue_id] })
      queryClient.invalidateQueries({ queryKey: ['job-dependencies'] })
      queryClient.invalidateQueries({ queryKey: ['job-dependents'] })
      break
    }
    case 'worker.heartbeat': {
      const payload = data as WsWorkerHeartbeatData
      stats.setWorkerStatus(payload.worker_id, payload.active_jobs > 0 ? 'busy' : 'idle')

      queryClient.setQueryData<Worker[]>(['workers'], (old) =>
        old?.map((w) =>
          w.id === payload.worker_id
            ? { ...w, current_jobs: payload.active_jobs, last_seen: ts }
            : w,
        ),
      )
      queryClient.setQueryData<WorkerDetail>(['worker', payload.worker_id], (old) => {
        if (!old) return old
        const heartbeat: WorkerHeartbeat = {
          id: `${payload.worker_id}-${ts}`,
          worker_id: payload.worker_id,
          ts,
          cpu_pct: payload.cpu_pct,
          mem_pct: payload.mem_pct,
          active_job_count: payload.active_jobs,
        }
        return {
          ...old,
          current_jobs: payload.active_jobs,
          last_seen: ts,
          heartbeats: [heartbeat, ...old.heartbeats].slice(0, 20),
        }
      })
      break
    }
    case 'worker.connected':
      stats.setWorkerStatus((data as { worker_id: string }).worker_id, 'idle')
      break
    case 'worker.disconnected':
      stats.setWorkerStatus((data as { worker_id: string }).worker_id, 'offline')
      break
    case 'queue.stats': {
      const payload = data as WsQueueStatsData
      stats.patchQueueStats(payload.queue_id, {
        pending_count: payload.pending_count,
        running_count: payload.running_count,
        failed_count: payload.failed_count,
      })
      queryClient.setQueryData(['queue', payload.queue_id], (old: unknown) => {
        if (!old || typeof old !== 'object') return old
        const queue = old as { stats: WsQueueStatsData }
        return { ...queue, stats: { ...queue.stats, ...payload } }
      })
      break
    }
    case 'queue.rate_limited': {
      const payload = data as WsQueueRateLimitedData
      stats.recordRateLimitEvent()
      useToastStore
        .getState()
        .addToast(
          'warning',
          `Queue ${payload.queue_name} is rate limited — ${payload.tokens_remaining.toFixed(1)} tokens remaining`,
        )
      queryClient.invalidateQueries({ queryKey: ['queue', payload.queue_id] })
      break
    }
    case 'queue.rebalancing': {
      const payload = data as WsQueueRebalancingData
      useToastStore
        .getState()
        .addToast(
          'warning',
          `Queue ${payload.queue_name} is rebalancing shards — workers will reassign within 15s`,
        )
      queryClient.invalidateQueries({ queryKey: ['shard-distribution', payload.queue_id] })
      break
    }
    case 'dlq.ai_summary_ready': {
      const payload = data as WsDlqAiSummaryReadyData
      queryClient.invalidateQueries({ queryKey: ['dlq-analysis', payload.dlq_id] })
      queryClient.invalidateQueries({ queryKey: ['dlq'] })
      useToastStore
        .getState()
        .addToast(
          'success',
          `AI analysis ready for '${payload.job_name}' — click to view`,
          `/dlq?expand=${payload.dlq_id}`,
        )
      break
    }
    default:
      break
  }
}

function connectSocket(token: string): void {
  if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
    return
  }

  intentionalClose = false
  useLiveStore.getState().setStatus(reconnectAttempt > 0 ? 'reconnecting' : 'connecting')

  const ws = new WebSocket(resolveWsUrl(token))
  socket = ws

  ws.onopen = () => {
    reconnectAttempt = 0
    useLiveStore.getState().setReconnectAttempt(0)
    useLiveStore.getState().setStatus('connected')
  }

  ws.onmessage = (event) => {
    try {
      handleEnvelope(JSON.parse(event.data) as WsEnvelope)
    } catch {
      // ignore malformed frames
    }
  }

  ws.onclose = () => {
    if (socket === ws) socket = null
    if (intentionalClose) {
      useLiveStore.getState().setStatus('disconnected')
      return
    }
    scheduleReconnect(token)
  }

  ws.onerror = () => {
    ws.close()
  }
}

function scheduleReconnect(token: string): void {
  if (reconnectTimer) return
  useLiveStore.getState().setStatus('reconnecting')
  const delay = RECONNECT_DELAYS_MS[Math.min(reconnectAttempt, RECONNECT_DELAYS_MS.length - 1)]
  reconnectAttempt += 1
  useLiveStore.getState().setReconnectAttempt(reconnectAttempt)
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null
    connectSocket(token)
  }, delay)
}

function disconnectSocket(): void {
  intentionalClose = true
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
  socket?.close()
  socket = null
  reconnectAttempt = 0
  useLiveStore.getState().setReconnectAttempt(0)
  useLiveStore.getState().setStatus('disconnected')
}

export function useWebSocket() {
  const token = useAuthStore((s) => s.token)

  useEffect(() => {
    if (!token) {
      disconnectSocket()
      return undefined
    }
    connectSocket(token)
    // No teardown here: connectSocket()/disconnectSocket() are idempotent
    // module-level singletons, so remounts (route changes, StrictMode) don't
    // spawn extra connections, and we only want to disconnect on logout.
    return undefined
  }, [token])

  const status = useLiveStore((s) => s.status)
  const events = useLiveStore((s) => s.events)
  const reconnectAttemptState = useLiveStore((s) => s.reconnectAttempt)

  return {
    status,
    lastEvent: events[0],
    eventHistory: events,
    reconnectAttempt: reconnectAttemptState,
  }
}
