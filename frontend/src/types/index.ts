// ---- Enums (mirrors backend Python enums exactly) ----

export type JobStatus =
  | 'queued'
  | 'scheduled'
  | 'claimed'
  | 'running'
  | 'completed'
  | 'failed'
  | 'dead'
  | 'cancelled'
  | 'blocked'

export type JobType = 'immediate' | 'delayed' | 'scheduled' | 'recurring' | 'batch'

export type WorkerStatus = 'idle' | 'busy' | 'offline'

export type RetryStrategy = 'fixed' | 'linear' | 'exponential'

export type LogLevel = 'debug' | 'info' | 'warning' | 'error'

export type UserRole = 'owner' | 'admin' | 'member' | 'viewer'

// ---- Envelope types ----

export interface PaginationMeta {
  total: number
  page: number
  limit: number
}

export interface DataResponse<T> {
  data: T
}

export interface PaginatedResponse<T> {
  data: T[]
  meta: PaginationMeta
}

export interface ApiErrorBody {
  error: {
    code: string
    message: string
    details: Record<string, unknown>
  }
}

// ---- Auth ----

export interface User {
  id: string
  org_id: string
  email: string
  full_name: string | null
  role: UserRole
  is_active: boolean
}

export interface TokenResponse {
  access_token: string
  token_type: string
  user: User
}

// ---- Organization / Project ----

export interface Organization {
  id: string
  name: string
  slug: string
  plan: string
  is_active: boolean
}

export interface Project {
  id: string
  org_id: string
  name: string
  slug: string
  description: string | null
  is_active: boolean
  created_at: string
  updated_at: string
}

// ---- Retry policy ----

export interface RetryPolicy {
  id: string
  name: string
  max_attempts: number
  strategy: RetryStrategy
  base_delay_seconds: number
  max_delay_seconds: number
  is_default: boolean
}

// ---- Queue ----

export interface QueueStats {
  pending_count: number
  running_count: number
  failed_count: number
  throughput_per_min: number
}

export interface Queue {
  id: string
  project_id: string
  name: string
  slug: string
  description: string | null
  priority: number
  concurrency_limit: number
  retry_policy_id: string | null
  is_paused: boolean
  is_active: boolean
  shard_count: number
  created_at: string
  updated_at: string
  stats: QueueStats
}

// ---- Job ----

export interface Job {
  id: string
  queue_id: string
  parent_job_id: string | null
  name: string
  status: JobStatus
  job_type: JobType
  priority: number
  scheduled_at: string | null
  run_at: string | null
  attempts: number
  max_attempts: number
  tags: string[]
  claimed_at: string | null
  started_at: string | null
  completed_at: string | null
  failed_at: string | null
  error_message: string | null
  worker_id: string | null
  created_at: string
  updated_at: string
}

export interface JobExecution {
  id: string
  job_id: string
  worker_id: string | null
  attempt_number: number
  status: JobStatus
  started_at: string | null
  completed_at: string | null
  duration_ms: number | null
  error_message: string | null
  result: Record<string, unknown> | null
}

export interface JobLog {
  id: string
  job_id: string
  execution_id: string | null
  level: LogLevel
  message: string
  timestamp: string
}

export interface JobDetail extends Job {
  payload: Record<string, unknown> | null
  result: Record<string, unknown> | null
  error_traceback: string | null
  cron_expression: string | null
  executions: JobExecution[]
  logs: JobLog[]
}

export interface JobCreateRequest {
  name: string
  payload: Record<string, unknown>
  job_type: JobType
  priority?: number
  run_at?: string
  cron_expression?: string
  scheduled_at?: string
  max_attempts?: number
  retry_strategy?: RetryStrategy
  base_delay_seconds?: number
  max_delay_seconds?: number
  max_runtime_seconds?: number
  tags?: string[]
  idempotency_key?: string
  depends_on?: string[]
}

// ---- Worker ----

export interface Worker {
  id: string
  queue_id: string
  hostname: string
  pid: number
  status: WorkerStatus
  max_concurrency: number
  current_jobs: number
  last_seen: string | null
  created_at: string
  updated_at: string
}

export interface WorkerHeartbeat {
  id: string
  worker_id: string
  ts: string
  cpu_pct: number | null
  mem_pct: number | null
  active_job_count: number
}

export interface WorkerDetail extends Worker {
  heartbeats: WorkerHeartbeat[]
}

// ---- Dead letter queue ----

export interface DeadLetterQueueEntry {
  id: string
  job_id: string
  queue_id: string
  job_name: string
  job_status: JobStatus
  failed_at: string
  total_attempts: number
  last_error: string
  last_traceback: string | null
  ai_summary: string | null
  is_resolved: boolean
  resolved_at: string | null
  resolved_by: string | null
  created_at: string
}

// ---- WebSocket events ----

export type WsEventName =
  | 'connection.established'
  | 'snapshot'
  | 'job.created'
  | 'job.claimed'
  | 'job.running'
  | 'job.updated'
  | 'job.completed'
  | 'job.failed'
  | 'job.dead'
  | 'worker.connected'
  | 'worker.disconnected'
  | 'worker.heartbeat'
  | 'queue.stats'

export interface WsEnvelope<T = unknown> {
  event: WsEventName
  data: T
  ts: string
}

export interface WsSnapshotData {
  active_workers: number
  queued_jobs: number
  running_jobs: number
}

export interface WsJobEventData {
  job_id: string
  name: string
  queue_id: string
  worker_id?: string | null
  attempts?: number
  max_attempts?: number
  started_at?: string
  duration_ms?: number
  error_message?: string
  next_retry_at?: string | null
  will_retry?: boolean
  total_attempts?: number
  last_error?: string
}

export interface WsWorkerHeartbeatData {
  worker_id: string
  hostname: string
  queue_id: string
  cpu_pct: number | null
  mem_pct: number | null
  active_jobs: number
  max_concurrency: number
}

export interface WsQueueStatsData {
  queue_id: string
  pending_count: number
  running_count: number
  failed_count: number
}
