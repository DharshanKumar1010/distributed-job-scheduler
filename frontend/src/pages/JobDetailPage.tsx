import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { cancelJob, retryJob } from '../api/jobs'
import { ErrorState } from '../components/ErrorState'
import { JsonViewer } from '../components/JsonViewer'
import { LogViewer } from '../components/LogViewer'
import { PageHeader } from '../components/PageHeader'
import { Skeleton } from '../components/Skeleton'
import { StatusBadge } from '../components/StatusBadge'
import { useJob } from '../hooks/useJobs'
import { formatDateTime } from '../lib/format'
import type { JobExecution } from '../types'

const CANCELLABLE = new Set(['queued', 'scheduled', 'blocked'])
const RETRYABLE = new Set(['failed', 'dead'])

function InfoRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="border-t border-border py-2 first:border-t-0">
      <div className="text-xs uppercase tracking-wide text-secondary">{label}</div>
      <div className="mt-0.5 text-sm text-primary">{value ?? '—'}</div>
    </div>
  )
}

function ExecutionRow({ execution }: { execution: JobExecution }) {
  const [open, setOpen] = useState(false)
  const hasError = !!execution.error_message

  return (
    <>
      <tr
        className="cursor-pointer border-t border-border transition-colors hover:bg-elevated"
        onClick={() => setOpen((o) => !o)}
      >
        <td className="px-4 py-2.5">
          <div className="flex items-center gap-2 text-primary">
            {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            <span className="font-mono text-xs text-mono">#{execution.attempt_number}</span>
          </div>
        </td>
        <td className="px-4 py-2.5">
          <StatusBadge status={execution.status} />
        </td>
        <td className="px-4 py-2.5 font-mono text-xs text-mono">
          {execution.started_at ? formatDateTime(execution.started_at) : '—'}
        </td>
        <td className="px-4 py-2.5 text-primary">
          {execution.duration_ms != null ? `${execution.duration_ms}ms` : '—'}
        </td>
      </tr>
      {open && (
        <tr className="border-t border-border">
          <td colSpan={4} className="px-4 py-3">
            {hasError ? (
              <div
                className="rounded-md border-l-2 bg-base p-3 font-mono text-xs text-danger"
                style={{ borderLeftColor: 'var(--danger)' }}
              >
                <div className="mb-1 font-medium">{execution.error_message}</div>
              </div>
            ) : (
              <JsonViewer data={execution.result} defaultOpen />
            )}
          </td>
        </tr>
      )}
    </>
  )
}

export function JobDetailPage() {
  const { jobId } = useParams<{ jobId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { data: job, isLoading, isError, refetch } = useJob(jobId)

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['job', jobId] })
    if (job) queryClient.invalidateQueries({ queryKey: ['jobs', job.queue_id] })
  }
  const cancelMutation = useMutation({ mutationFn: () => cancelJob(jobId as string), onSuccess: invalidate })
  const retryMutation = useMutation({ mutationFn: () => retryJob(jobId as string), onSuccess: invalidate })

  if (isLoading) {
    return (
      <div className="rounded-lg border border-border bg-card p-6">
        <Skeleton rows={5} />
      </div>
    )
  }

  if (isError || !job) {
    return <ErrorState message="Couldn't load job" onRetry={() => refetch()} />
  }

  return (
    <div>
      <PageHeader
        title={job.name}
        description={`Queue ${job.queue_id}`}
        actions={
          <div className="flex gap-2">
            {CANCELLABLE.has(job.status) && (
              <button
                type="button"
                onClick={() => cancelMutation.mutate()}
                disabled={cancelMutation.isPending}
                className="rounded-md border border-border px-3 py-1.5 text-sm text-danger transition-colors hover:bg-elevated disabled:opacity-50"
              >
                Cancel
              </button>
            )}
            {RETRYABLE.has(job.status) && (
              <button
                type="button"
                onClick={() => retryMutation.mutate()}
                disabled={retryMutation.isPending}
                className="rounded-md bg-accent px-3 py-1.5 text-sm text-white transition-opacity hover:opacity-90 disabled:opacity-50"
              >
                Retry
              </button>
            )}
            <button
              type="button"
              onClick={() => navigate(-1)}
              className="rounded-md border border-border px-3 py-1.5 text-sm text-secondary transition-colors hover:bg-elevated"
            >
              Back
            </button>
          </div>
        }
      />

      {/* A. Job info */}
      <div className="rounded-lg border border-border bg-card p-5">
        <div className="grid grid-cols-2 gap-x-8">
          <InfoRow label="Status" value={<StatusBadge status={job.status} />} />
          <InfoRow label="Type" value={job.job_type} />
          <InfoRow label="Priority" value={job.priority} />
          <InfoRow label="Attempts" value={`${job.attempts} / ${job.max_attempts}`} />
          <InfoRow label="Worker" value={job.worker_id} />
          <InfoRow label="Created" value={formatDateTime(job.created_at)} />
          <InfoRow label="Started" value={job.started_at ? formatDateTime(job.started_at) : null} />
          <InfoRow label="Completed" value={job.completed_at ? formatDateTime(job.completed_at) : null} />
          <InfoRow label="Scheduled at" value={job.scheduled_at ? formatDateTime(job.scheduled_at) : null} />
          <InfoRow label="Cron" value={job.cron_expression} />
        </div>

        {job.error_message && (
          <div className="mt-3 rounded-md border-l-2 bg-base p-3 font-mono text-xs text-danger" style={{ borderLeftColor: 'var(--danger)' }}>
            {job.error_message}
          </div>
        )}

        <div className="mt-4">
          <div className="mb-1.5 text-xs uppercase tracking-wide text-secondary">Payload</div>
          <JsonViewer data={job.payload} />
        </div>
      </div>

      {/* B. Execution history */}
      <div className="mt-6 overflow-hidden rounded-lg border border-border bg-card">
        <div className="border-b border-border px-5 py-3 text-xs uppercase tracking-widest text-secondary">
          Execution history
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wider text-secondary">
              <th className="px-4 py-2.5 font-medium">Attempt</th>
              <th className="px-4 py-2.5 font-medium">Status</th>
              <th className="px-4 py-2.5 font-medium">Started</th>
              <th className="px-4 py-2.5 font-medium">Duration</th>
            </tr>
          </thead>
          <tbody>
            {job.executions.map((execution) => (
              <ExecutionRow key={execution.id} execution={execution} />
            ))}
            {job.executions.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-6 text-center text-secondary">
                  No executions yet
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* C. Logs */}
      <div className="mt-6 rounded-lg border border-border bg-card p-5">
        <div className="mb-3 text-xs uppercase tracking-widest text-secondary">Logs</div>
        <LogViewer logs={job.logs} />
      </div>
    </div>
  )
}
