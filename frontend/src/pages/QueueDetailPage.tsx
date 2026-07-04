import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { cancelJob, retryJob } from '../api/jobs'
import { updateQueue } from '../api/queues'
import { ErrorState } from '../components/ErrorState'
import { PageHeader } from '../components/PageHeader'
import { Skeleton } from '../components/Skeleton'
import { StatusBadge } from '../components/StatusBadge'
import { useJobs } from '../hooks/useJobs'
import { useDefaultProject } from '../hooks/useProject'
import { useQueue } from '../hooks/useQueue'
import { useRetryPolicies } from '../hooks/useRetryPolicies'
import { formatRelativeAge, truncateId } from '../lib/format'
import type { Job } from '../types'

const CANCELLABLE = new Set(['queued', 'scheduled', 'blocked'])
const RETRYABLE = new Set(['failed', 'dead'])

const fieldInputClass =
  'w-full rounded-md border border-border bg-elevated px-3 py-2 text-sm text-primary outline-none transition-shadow focus:shadow-[0_0_0_2px_var(--accent-glow)]'

function JobRowActions({ job }: { job: Job }) {
  const queryClient = useQueryClient()
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['jobs', job.queue_id] })

  const cancelMutation = useMutation({ mutationFn: () => cancelJob(job.id), onSuccess: invalidate })
  const retryMutation = useMutation({ mutationFn: () => retryJob(job.id), onSuccess: invalidate })

  if (CANCELLABLE.has(job.status)) {
    return (
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation()
          cancelMutation.mutate()
        }}
        disabled={cancelMutation.isPending}
        className="text-xs text-danger hover:underline disabled:opacity-50"
      >
        Cancel
      </button>
    )
  }

  if (RETRYABLE.has(job.status)) {
    return (
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation()
          retryMutation.mutate()
        }}
        disabled={retryMutation.isPending}
        className="text-xs text-accent hover:underline disabled:opacity-50"
      >
        Retry
      </button>
    )
  }

  return <span className="text-xs text-secondary">—</span>
}

export function QueueDetailPage() {
  const { queueId } = useParams<{ queueId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const { data: project } = useDefaultProject()
  const { data: queue, isLoading, isError, refetch } = useQueue(project?.id, queueId)
  const { data: jobsResult, isLoading: jobsLoading } = useJobs(queueId, { limit: 50 })
  const { data: retryPolicies } = useRetryPolicies()

  const [concurrencyLimit, setConcurrencyLimit] = useState(0)
  const [priority, setPriority] = useState(0)
  const [retryPolicyId, setRetryPolicyId] = useState('')

  useEffect(() => {
    if (queue) {
      setConcurrencyLimit(queue.concurrency_limit)
      setPriority(queue.priority)
      setRetryPolicyId(queue.retry_policy_id ?? '')
    }
  }, [queue])

  const isDirty =
    !!queue &&
    (concurrencyLimit !== queue.concurrency_limit ||
      priority !== queue.priority ||
      retryPolicyId !== (queue.retry_policy_id ?? ''))

  const saveMutation = useMutation({
    mutationFn: () =>
      updateQueue(project!.id, queueId as string, {
        concurrency_limit: concurrencyLimit,
        priority,
        retry_policy_id: retryPolicyId || null,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['queue', project?.id, queueId] })
      queryClient.invalidateQueries({ queryKey: ['queues', project?.id] })
    },
  })

  if (isLoading) {
    return (
      <div className="rounded-lg border border-border bg-card p-6">
        <Skeleton rows={5} />
      </div>
    )
  }

  if (isError || !queue) {
    return <ErrorState message="Couldn't load queue" onRetry={() => refetch()} />
  }

  return (
    <div>
      <PageHeader title={queue.name} description={queue.description ?? undefined} />

      <div className="flex gap-6">
        <div className="w-[65%] overflow-hidden rounded-lg border border-border bg-card">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wider text-secondary">
                <th className="px-4 py-3 font-medium">ID</th>
                <th className="px-4 py-3 font-medium">Name</th>
                <th className="px-4 py-3 font-medium">Type</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Priority</th>
                <th className="px-4 py-3 font-medium">Attempts</th>
                <th className="px-4 py-3 font-medium">Age</th>
                <th className="px-4 py-3 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {jobsLoading && (
                <tr>
                  <td colSpan={8} className="px-4 py-6">
                    <Skeleton rows={3} />
                  </td>
                </tr>
              )}
              {!jobsLoading &&
                jobsResult?.data.map((job) => (
                  <tr
                    key={job.id}
                    onClick={() => navigate(`/jobs/${job.id}`)}
                    className="cursor-pointer border-t border-border transition-colors hover:bg-elevated"
                  >
                    <td className="px-4 py-3 font-mono text-xs text-mono">{truncateId(job.id)}</td>
                    <td className="px-4 py-3 text-primary">{job.name}</td>
                    <td className="px-4 py-3 text-secondary">{job.job_type}</td>
                    <td className="px-4 py-3">
                      <StatusBadge status={job.status} />
                    </td>
                    <td className="px-4 py-3 text-primary">{job.priority}</td>
                    <td className="px-4 py-3 text-primary">
                      {job.attempts}/{job.max_attempts}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-mono">
                      {formatRelativeAge(job.created_at)}
                    </td>
                    <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                      <JobRowActions job={job} />
                    </td>
                  </tr>
                ))}
              {!jobsLoading && (jobsResult?.data.length ?? 0) === 0 && (
                <tr>
                  <td colSpan={8} className="px-4 py-8 text-center text-secondary">
                    No jobs in this queue yet
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="w-[35%] rounded-lg border border-border bg-card p-5">
          <div className="mb-4 text-xs uppercase tracking-widest text-secondary">Configuration</div>

          <div className="space-y-4">
            <div>
              <label className="mb-1.5 block text-xs text-secondary">Concurrency limit</label>
              <input
                type="number"
                min={1}
                value={concurrencyLimit}
                onChange={(e) => setConcurrencyLimit(Number(e.target.value))}
                className={fieldInputClass}
              />
            </div>

            <div>
              <label className="mb-1.5 block text-xs text-secondary">Priority</label>
              <input
                type="number"
                min={0}
                max={10}
                value={priority}
                onChange={(e) => setPriority(Number(e.target.value))}
                className={fieldInputClass}
              />
            </div>

            <div>
              <label className="mb-1.5 block text-xs text-secondary">Retry policy</label>
              <select
                value={retryPolicyId}
                onChange={(e) => setRetryPolicyId(e.target.value)}
                className={fieldInputClass}
              >
                <option value="">None</option>
                {retryPolicies?.map((policy) => (
                  <option key={policy.id} value={policy.id}>
                    {policy.name}
                  </option>
                ))}
              </select>
            </div>

            {isDirty && (
              <button
                type="button"
                onClick={() => saveMutation.mutate()}
                disabled={saveMutation.isPending}
                className="w-full rounded-md bg-accent py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
              >
                {saveMutation.isPending ? 'Saving…' : 'Save changes'}
              </button>
            )}
          </div>

          <div className="mt-6 border-t border-border pt-4 text-xs text-secondary">
            <div className="flex justify-between py-1">
              <span>Pending</span>
              <span className="text-primary">{queue.stats.pending_count}</span>
            </div>
            <div className="flex justify-between py-1">
              <span>Running</span>
              <span className="text-primary">{queue.stats.running_count}</span>
            </div>
            <div className="flex justify-between py-1">
              <span>Failed</span>
              <span className="text-primary">{queue.stats.failed_count}</span>
            </div>
            <div className="flex justify-between py-1">
              <span>Throughput/min</span>
              <span className="text-primary">{queue.stats.throughput_per_min}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
