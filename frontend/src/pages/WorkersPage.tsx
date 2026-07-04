import { useEffect } from 'react'
import { ErrorState } from '../components/ErrorState'
import { PageHeader } from '../components/PageHeader'
import { Skeleton } from '../components/Skeleton'
import { WorkerCard } from '../components/WorkerCard'
import { useDefaultProject } from '../hooks/useProject'
import { useQueues } from '../hooks/useQueue'
import { useWorkers } from '../hooks/useWorkers'
import { useLiveStatsStore } from '../store/liveStatsStore'

export function WorkersPage() {
  const { data: project } = useDefaultProject()
  const { data: queues } = useQueues(project?.id)
  const { data: workers, isLoading, isError, refetch } = useWorkers()
  const seedWorkers = useLiveStatsStore((s) => s.seedWorkers)

  // Seed live status from this page's own fetch too — DashboardPage isn't
  // guaranteed to have run first if the user lands here directly.
  useEffect(() => {
    if (workers) seedWorkers(workers)
  }, [workers, seedWorkers])

  const queueNameById = new Map((queues ?? []).map((q) => [q.id, q.name]))

  return (
    <div>
      <PageHeader title="Workers" description="Active worker processes across your queues" />

      {isLoading && (
        <div className="rounded-lg border border-border bg-card p-6">
          <Skeleton rows={4} />
        </div>
      )}

      {!isLoading && isError && (
        <ErrorState message="Couldn't load workers" onRetry={() => refetch()} />
      )}

      {!isLoading && !isError && workers && workers.length === 0 && (
        <div className="rounded-lg border border-border bg-card py-16 text-center text-sm text-secondary">
          No workers registered yet
        </div>
      )}

      {!isLoading && !isError && workers && workers.length > 0 && (
        <div className="grid grid-cols-3 gap-4">
          {workers.map((worker) => (
            <WorkerCard key={worker.id} worker={worker} queueName={queueNameById.get(worker.queue_id)} />
          ))}
        </div>
      )}
    </div>
  )
}
