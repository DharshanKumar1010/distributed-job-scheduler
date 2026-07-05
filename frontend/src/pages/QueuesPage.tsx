import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Settings, Trash2 } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { createQueue, deleteQueue, pauseQueue, resumeQueue } from '../api/queues'
import { ErrorState } from '../components/ErrorState'
import { PageHeader } from '../components/PageHeader'
import { PulseRing } from '../components/PulseRing'
import { Skeleton } from '../components/Skeleton'
import { usePermissions } from '../hooks/usePermissions'
import { useQueues } from '../hooks/useQueue'
import { useDefaultProject } from '../hooks/useProject'
import type { Queue } from '../types'

function PauseToggle({ queue, projectId, disabled }: { queue: Queue; projectId: string; disabled: boolean }) {
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
      disabled={disabled || mutation.isPending}
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

function CreateQueueForm({ projectId }: { projectId: string }) {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const queryClient = useQueryClient()

  const mutation = useMutation({
    mutationFn: () =>
      createQueue(projectId, {
        name,
        slug: name
          .trim()
          .toLowerCase()
          .replace(/[^a-z0-9]+/g, '-')
          .replace(/(^-|-$)/g, ''),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['queues', projectId] })
      setName('')
      setOpen(false)
    },
  })

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (name.trim()) mutation.mutate()
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-white transition-opacity hover:opacity-90"
      >
        Create Queue
      </button>
    )
  }

  return (
    <form onSubmit={handleSubmit} className="flex items-center gap-2">
      <input
        autoFocus
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder="Queue name"
        className="rounded-md border border-border bg-elevated px-3 py-1.5 text-sm text-primary outline-none focus:shadow-[0_0_0_2px_var(--accent-glow)]"
      />
      <button
        type="submit"
        disabled={mutation.isPending || !name.trim()}
        className="rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
      >
        {mutation.isPending ? 'Creating…' : 'Create'}
      </button>
      <button
        type="button"
        onClick={() => setOpen(false)}
        className="rounded-md border border-border px-3 py-1.5 text-sm text-secondary transition-colors hover:bg-elevated"
      >
        Cancel
      </button>
    </form>
  )
}

export function QueuesPage() {
  const navigate = useNavigate()
  const { can } = usePermissions()
  const { data: project, isLoading: projectLoading } = useDefaultProject()
  const { data: queues, isLoading, isError, refetch } = useQueues(project?.id)
  const queryClient = useQueryClient()

  const deleteMutation = useMutation({
    mutationFn: (queueId: string) => deleteQueue(project!.id, queueId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['queues', project?.id] }),
  })

  const loading = projectLoading || isLoading

  return (
    <div>
      <PageHeader
        title="Queues"
        description="Manage job queues and their throughput"
        actions={project && can('queue:create') ? <CreateQueueForm projectId={project.id} /> : undefined}
      />

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
                      <PauseToggle queue={queue} projectId={project!.id} disabled={!can('queue:pause')} />
                      {can('queue:configure') && (
                        <button
                          type="button"
                          onClick={() => navigate(`/queues/${queue.id}`)}
                          className="rounded-md p-1.5 text-secondary transition-colors hover:bg-base hover:text-primary"
                          aria-label={`Configure ${queue.name}`}
                        >
                          <Settings size={16} />
                        </button>
                      )}
                      {can('queue:delete') && (
                        <button
                          type="button"
                          onClick={() => {
                            if (window.confirm(`Delete queue "${queue.name}"?`)) {
                              deleteMutation.mutate(queue.id)
                            }
                          }}
                          disabled={deleteMutation.isPending}
                          className="rounded-md p-1.5 text-secondary transition-colors hover:bg-base hover:text-danger disabled:opacity-50"
                          aria-label={`Delete ${queue.name}`}
                        >
                          <Trash2 size={16} />
                        </button>
                      )}
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
