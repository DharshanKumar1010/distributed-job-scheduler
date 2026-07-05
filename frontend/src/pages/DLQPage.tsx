import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ChevronDown, ChevronRight, Loader2 } from 'lucide-react'
import { useState } from 'react'
import { replayDlqEntry, resolveDlqEntry } from '../api/dlq'
import { ErrorState } from '../components/ErrorState'
import { PageHeader } from '../components/PageHeader'
import { Skeleton } from '../components/Skeleton'
import { StatusBadge } from '../components/StatusBadge'
import { useDlqEntries } from '../hooks/useDlq'
import { useDefaultProject } from '../hooks/useProject'
import { usePermissions } from '../hooks/usePermissions'
import { useQueues } from '../hooks/useQueue'
import { formatDateTime, truncateId } from '../lib/format'
import type { DeadLetterQueueEntry } from '../types'

function truncate(text: string, length: number): string {
  return text.length > length ? `${text.slice(0, length)}…` : text
}

function DlqRow({ entry, queueName }: { entry: DeadLetterQueueEntry; queueName?: string }) {
  const [open, setOpen] = useState(false)
  const queryClient = useQueryClient()
  const { can } = usePermissions()
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['dlq'] })

  const resolveMutation = useMutation({ mutationFn: () => resolveDlqEntry(entry.id), onSuccess: invalidate })
  const replayMutation = useMutation({ mutationFn: () => replayDlqEntry(entry.id), onSuccess: invalidate })

  return (
    <>
      <tr
        className="cursor-pointer border-t border-border transition-colors hover:bg-elevated"
        onClick={() => setOpen((o) => !o)}
      >
        <td className="px-4 py-3">
          <div className="flex items-center gap-2 text-primary">
            {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            {entry.job_name}
          </div>
        </td>
        <td className="px-4 py-3 text-secondary">{queueName ?? truncateId(entry.queue_id)}</td>
        <td className="px-4 py-3 font-mono text-xs text-mono">{formatDateTime(entry.failed_at)}</td>
        <td className="px-4 py-3 text-primary">{entry.total_attempts}</td>
        <td className="px-4 py-3 font-mono text-xs text-secondary">{truncate(entry.last_error, 50)}</td>
        <td className="px-4 py-3">
          <StatusBadge status={entry.is_resolved ? 'resolved' : 'unresolved'} />
        </td>
        <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
          <div className="flex gap-3">
            {can('dlq:replay') && (
              <button
                type="button"
                onClick={() => replayMutation.mutate()}
                disabled={replayMutation.isPending}
                className="text-xs text-accent hover:underline disabled:opacity-50"
              >
                Replay
              </button>
            )}
            {can('dlq:resolve') && (
              <button
                type="button"
                onClick={() => resolveMutation.mutate()}
                disabled={entry.is_resolved || resolveMutation.isPending}
                className="text-xs text-secondary hover:text-primary hover:underline disabled:opacity-50"
              >
                Resolve
              </button>
            )}
          </div>
        </td>
      </tr>
      {open && (
        <tr className="border-t border-border">
          <td colSpan={7} className="px-4 py-4">
            <div className="space-y-3">
              <div>
                <div className="mb-1 text-xs uppercase tracking-wide text-secondary">Last error</div>
                <div className="font-mono text-xs text-danger">{entry.last_error}</div>
              </div>

              {entry.last_traceback && (
                <div>
                  <div className="mb-1 text-xs uppercase tracking-wide text-secondary">Traceback</div>
                  <pre
                    className="overflow-x-auto rounded-md border-l-2 bg-base p-3 font-mono text-xs text-secondary"
                    style={{ borderLeftColor: 'var(--danger)' }}
                  >
                    {entry.last_traceback}
                  </pre>
                </div>
              )}

              <div>
                <div className="mb-1 text-xs uppercase tracking-wide text-secondary">AI summary</div>
                <div
                  className="rounded-md border-l-2 bg-card p-3 text-sm italic text-secondary"
                  style={{ borderLeftColor: 'var(--accent)' }}
                >
                  {entry.ai_summary ?? (
                    <span className="inline-flex items-center gap-2 not-italic">
                      <Loader2 size={14} className="animate-spin text-accent" />
                      Generating summary…
                    </span>
                  )}
                </div>
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  )
}

export function DLQPage() {
  const { data: project } = useDefaultProject()
  const { data: queues } = useQueues(project?.id)
  const { data: result, isLoading, isError, refetch } = useDlqEntries({ limit: 50 })

  const queueNameById = new Map((queues ?? []).map((q) => [q.id, q.name]))

  return (
    <div>
      <PageHeader title="Dead Letter Queue" description="Jobs that exhausted all retry attempts" />

      {isLoading && (
        <div className="rounded-lg border border-border bg-card p-6">
          <Skeleton rows={4} />
        </div>
      )}

      {!isLoading && isError && <ErrorState message="Couldn't load DLQ entries" onRetry={() => refetch()} />}

      {!isLoading && !isError && result && (
        <div className="overflow-hidden rounded-lg border border-border bg-card">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wider text-secondary">
                <th className="px-4 py-3 font-medium">Job</th>
                <th className="px-4 py-3 font-medium">Queue</th>
                <th className="px-4 py-3 font-medium">Failed At</th>
                <th className="px-4 py-3 font-medium">Attempts</th>
                <th className="px-4 py-3 font-medium">Last Error</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {result.data.map((entry) => (
                <DlqRow key={entry.id} entry={entry} queueName={queueNameById.get(entry.queue_id)} />
              ))}
              {result.data.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-secondary">
                    Nothing in the dead letter queue
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
