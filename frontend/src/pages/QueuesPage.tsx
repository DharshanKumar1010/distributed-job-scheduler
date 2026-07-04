import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Settings } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { pauseQueue, resumeQueue } from '../api/queues'
import { ErrorState } from '../components/ErrorState'
import { PageHeader } from '../components/PageHeader'
import { PulseRing } from '../components/PulseRing'
import { Skeleton } from '../components/Skeleton'
import { useQueues } from '../hooks/useQueue'
import { useDefaultProject } from '../hooks/useProject'
import type { Queue } from '../types'

function PauseToggle({ queue, projectId }: { queue: Queue; projectId: string }) {
  const queryClient = useQueryClient()
  const mutation = useMutation({
    mutationFn: () => (queue.is_paused ? resumeQueue(projectId, queue.id) : pauseQueue(projectId, queue.id)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['queues', projectId] })
    },
  })

  const isActive = !queue.is_paused

  return (
    <button
      type="button"
      role="switch"
      aria-checked={isActive}
      disabled={mutation.isPending}
      onClick={() => mutation.mutate()}
      className="relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors disabled:opacity-50"
      style={{ backgroundColor: isActive ? 'var(--accent)' : 'var(--border)' }}
    >
      <span
        className="inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform"
        style={{ transform: isActive ? 'translateX(18px)' : 'translateX(3px)' }}
      />
    </button>
  )
}

export function QueuesPage() {
  const navigate = useNavigate()
  const { data: project, isLoading: projectLoading } = useDefaultProject()
  const { data: queues, isLoading, isError, refetch } = useQueues(project?.id)

  const loading = projectLoading || isLoading

  return (
    <div>
      <PageHeader title="Queues" description="Manage job queues and their throughput" />

      {loading && (
        <div className="rounded-lg border border-border bg-card p-6">
          <Skeleton rows={4} />
        </div>
      )}

      {!loading && isError && <ErrorState message="Couldn't load queues" onRetry={() => refetch()} />}

      {!loading && !isError && queues && (
        <div className="overflow-hidden rounded-lg border border-border bg-card">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wider text-secondary">
                <th className="px-4 py-3 font-medium">Name</th>
                <th className="px-4 py-3 font-medium">Pending</th>
                <th className="px-4 py-3 font-medium">Running</th>
                <th className="px-4 py-3 font-medium">Failed</th>
                <th className="px-4 py-3 font-medium">Rate Limit</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {queues.map((queue) => (
                <tr
                  key={queue.id}
                  className="cursor-pointer border-t border-border transition-colors hover:bg-elevated"
                  onClick={() => navigate(`/queues/${queue.id}`)}
                >
                  <td className="px-4 py-3 text-primary">{queue.name}</td>
                  <td className="px-4 py-3 text-primary">{queue.stats.pending_count}</td>
                  <td className="px-4 py-3 text-primary">{queue.stats.running_count}</td>
                  <td className="px-4 py-3 text-primary">{queue.stats.failed_count}</td>
                  <td className="px-4 py-3 text-primary">{queue.concurrency_limit}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <PulseRing color={queue.is_paused ? 'warning' : 'success'} pulse={!queue.is_paused} />
                      <span className="text-secondary">{queue.is_paused ? 'Paused' : 'Active'}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-3" onClick={(e) => e.stopPropagation()}>
                      <PauseToggle queue={queue} projectId={project!.id} />
                      <button
                        type="button"
                        onClick={() => navigate(`/queues/${queue.id}`)}
                        className="rounded-md p-1.5 text-secondary transition-colors hover:bg-base hover:text-primary"
                        aria-label={`Configure ${queue.name}`}
                      >
                        <Settings size={16} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {queues.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-4 py-8 text-center text-secondary">
                    No queues yet
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
