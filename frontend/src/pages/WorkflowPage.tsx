import { useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { DagCanvas, type DagEdge, type DagNode } from '../components/DagCanvas'
import { ErrorState } from '../components/ErrorState'
import { JsonViewer } from '../components/JsonViewer'
import { PageHeader } from '../components/PageHeader'
import { Skeleton } from '../components/Skeleton'
import { StatusBadge } from '../components/StatusBadge'
import { useCreateWorkflow, useJobDependencies } from '../hooks/useDependencies'
import { useJob, useJobs } from '../hooks/useJobs'
import { usePermissions } from '../hooks/usePermissions'
import { useDefaultProject } from '../hooks/useProject'
import { useQueues } from '../hooks/useQueue'
import { useLiveStore } from '../store/liveStore'
import type { DependencyGraph, DependencyNode, JobStatus, WsJobEventData } from '../types'

const LIVE_EVENTS = new Set([
  'job.claimed',
  'job.running',
  'job.completed',
  'job.failed',
  'job.dead',
  'job.unblocked',
])

function statusFromLiveEvent(event: string, payload: WsJobEventData): JobStatus | null {
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

function flattenGraph(root: DependencyNode): { nodes: DagNode[]; edges: DagEdge[] } {
  const nodes = new Map<string, DagNode>()
  const edgeKeys = new Map<string, DagEdge>()

  const upsertNode = (n: DependencyNode) => {
    if (!nodes.has(n.job_id)) nodes.set(n.job_id, { id: n.job_id, name: n.name, status: n.status })
  }

  const visitAncestors = (node: DependencyNode) => {
    upsertNode(node)
    for (const dep of node.depends_on) {
      upsertNode(dep)
      edgeKeys.set(`${dep.job_id}->${node.job_id}`, { from: dep.job_id, to: node.job_id })
      visitAncestors(dep)
    }
  }

  const visitDescendants = (node: DependencyNode) => {
    upsertNode(node)
    for (const dep of node.dependents) {
      upsertNode(dep)
      edgeKeys.set(`${node.job_id}->${dep.job_id}`, { from: node.job_id, to: dep.job_id })
      visitDescendants(dep)
    }
  }

  visitAncestors(root)
  visitDescendants(root)

  return { nodes: Array.from(nodes.values()), edges: Array.from(edgeKeys.values()) }
}

function WorkflowStatsPanel({ graph }: { graph: DependencyGraph }) {
  const ws = graph.workflow_status
  const rows: Array<[string, number]> = [
    ['Queued', ws.queued],
    ['Blocked', ws.blocked],
    ['Running', ws.running],
    ['Completed', ws.completed],
    ['Failed', ws.failed],
    ['Dead', ws.dead],
  ]

  return (
    <div>
      <div className="mb-4 text-xs uppercase tracking-widest text-secondary">Workflow progress</div>
      <div className="mb-4 h-2 w-full overflow-hidden rounded-full bg-elevated">
        <div
          className="h-full rounded-full bg-success transition-all duration-300"
          style={{ width: `${ws.progress_pct}%` }}
        />
      </div>
      <div className="mb-5 text-sm text-secondary">{ws.progress_pct.toFixed(0)}% complete</div>
      <div className="space-y-2">
        {rows.map(([label, value]) => (
          <div key={label} className="flex items-center justify-between text-sm">
            <span className="text-secondary">{label}</span>
            <span className="font-mono text-primary">{value}</span>
          </div>
        ))}
      </div>
      <div className="mt-4 border-t border-border pt-3 text-xs text-secondary">
        {ws.total} job{ws.total === 1 ? '' : 's'} total in this workflow
      </div>
    </div>
  )
}

function NodeDetailPanel({ jobId }: { jobId: string }) {
  const { data: job, isLoading } = useJob(jobId)
  const navigate = useNavigate()

  if (isLoading || !job) {
    return <Skeleton rows={4} />
  }

  return (
    <div>
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="min-w-0 truncate font-display text-base text-primary">{job.name}</div>
        <StatusBadge status={job.status} />
      </div>
      <div className="mb-1 text-xs uppercase tracking-wide text-secondary">Payload</div>
      <JsonViewer data={job.payload} defaultOpen={false} />

      {job.executions.length > 0 && (
        <div className="mt-4">
          <div className="mb-1 text-xs uppercase tracking-wide text-secondary">Last execution</div>
          <div className="rounded-md border border-border bg-base p-3 text-sm text-secondary">
            <div>
              Attempt #{job.executions[job.executions.length - 1].attempt_number} —{' '}
              <StatusBadge status={job.executions[job.executions.length - 1].status} />
            </div>
            {job.executions[job.executions.length - 1].duration_ms != null && (
              <div className="mt-1 font-mono text-xs text-mono">
                {job.executions[job.executions.length - 1].duration_ms}ms
              </div>
            )}
          </div>
        </div>
      )}

      <button
        type="button"
        onClick={() => navigate(`/jobs/${job.id}`)}
        className="mt-4 text-sm text-accent transition-opacity hover:opacity-80"
      >
        View full detail →
      </button>
    </div>
  )
}

const WORKFLOW_TEMPLATE = `{
  "name": "my-workflow",
  "jobs": [
    { "ref": "step-a", "name": "step-a", "queue_id": "REPLACE_WITH_QUEUE_ID", "payload": {} },
    { "ref": "step-b", "name": "step-b", "queue_id": "REPLACE_WITH_QUEUE_ID", "payload": {}, "depends_on": ["step-a"] }
  ]
}`

function CreateWorkflowForm() {
  const [open, setOpen] = useState(false)
  const [json, setJson] = useState(WORKFLOW_TEMPLATE)
  const [error, setError] = useState<string | null>(null)
  const mutation = useCreateWorkflow()

  const handleSubmit = () => {
    setError(null)
    try {
      const payload = JSON.parse(json)
      mutation.mutate(payload, {
        onSuccess: () => setOpen(false),
        onError: () => setError('Failed to create workflow - check the payload shape'),
      })
    } catch {
      setError('Invalid JSON')
    }
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-white transition-opacity hover:opacity-90"
      >
        Create Workflow
      </button>
    )
  }

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/50">
      <div className="w-[520px] rounded-lg border border-border bg-card p-5">
        <div className="mb-3 text-sm font-medium text-primary">Create Workflow</div>
        <textarea
          value={json}
          onChange={(e) => setJson(e.target.value)}
          rows={12}
          className="w-full rounded-md border border-border bg-elevated p-3 font-mono text-xs text-primary outline-none focus:shadow-[0_0_0_2px_var(--accent-glow)]"
        />
        {error && <div className="mt-2 text-xs text-danger">{error}</div>}
        <div className="mt-3 flex justify-end gap-2">
          <button
            type="button"
            onClick={() => setOpen(false)}
            className="rounded-md border border-border px-3 py-1.5 text-sm text-secondary transition-colors hover:bg-elevated"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={mutation.isPending}
            className="rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            {mutation.isPending ? 'Creating…' : 'Create'}
          </button>
        </div>
      </div>
    </div>
  )
}

export function WorkflowPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const rootJobId = searchParams.get('job') ?? undefined
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const { can } = usePermissions()

  const { data: project } = useDefaultProject()
  const { data: queues } = useQueues(project?.id)
  const [queueId, setQueueId] = useState<string | undefined>(undefined)
  const activeQueueId = queueId ?? queues?.[0]?.id
  const { data: jobsPage } = useJobs(activeQueueId, { limit: 50, sort: 'created_at' })

  const { data: graph, isLoading, isError, refetch } = useJobDependencies(rootJobId)

  const events = useLiveStore((s) => s.events)
  const liveStatuses = useMemo(() => {
    const map: Record<string, JobStatus> = {}
    for (const evt of events) {
      if (!LIVE_EVENTS.has(evt.event)) continue
      const payload = evt.data as WsJobEventData
      if (map[payload.job_id]) continue
      const status = statusFromLiveEvent(evt.event, payload)
      if (status) map[payload.job_id] = status
    }
    return map
  }, [events])

  const { nodes, edges } = useMemo(() => (graph ? flattenGraph(graph) : { nodes: [], edges: [] }), [graph])

  return (
    <div>
      <PageHeader
        title="Workflows"
        description="Visualize job dependency graphs (DAGs) live"
        actions={can('workflow:create') ? <CreateWorkflowForm /> : undefined}
      />

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <select
          value={activeQueueId ?? ''}
          onChange={(e) => setQueueId(e.target.value)}
          className="rounded-md border border-border bg-card px-3 py-1.5 text-sm text-primary"
        >
          {(queues ?? []).map((q) => (
            <option key={q.id} value={q.id}>
              {q.name}
            </option>
          ))}
        </select>
        <select
          value={rootJobId ?? ''}
          onChange={(e) => {
            setSearchParams(e.target.value ? { job: e.target.value } : {})
            setSelectedNodeId(null)
          }}
          className="min-w-[220px] rounded-md border border-border bg-card px-3 py-1.5 text-sm text-primary"
        >
          <option value="">Select a job to view its workflow…</option>
          {(jobsPage?.data ?? []).map((job) => (
            <option key={job.id} value={job.id}>
              {job.name}
            </option>
          ))}
        </select>
      </div>

      <div className="grid grid-cols-3 gap-6">
        <div className="col-span-2 rounded-lg border border-border bg-card p-5">
          <div className="mb-3 text-xs uppercase tracking-widest text-secondary">Workflow builder</div>

          {!rootJobId && (
            <div className="flex h-64 items-center justify-center text-sm text-secondary">
              Pick a job above to see its dependency graph
            </div>
          )}

          {rootJobId && isLoading && <Skeleton rows={6} />}

          {rootJobId && isError && <ErrorState message="Couldn't load workflow" onRetry={() => refetch()} />}

          {rootJobId && graph && (
            <DagCanvas
              nodes={nodes}
              edges={edges}
              selectedId={selectedNodeId}
              onNodeClick={setSelectedNodeId}
              liveStatuses={liveStatuses}
            />
          )}
        </div>

        <div className="rounded-lg border border-border bg-card p-5">
          {selectedNodeId ? (
            <NodeDetailPanel jobId={selectedNodeId} />
          ) : graph ? (
            <WorkflowStatsPanel graph={graph} />
          ) : (
            <div className="text-sm text-secondary">Select a job to see workflow stats</div>
          )}
        </div>
      </div>
    </div>
  )
}
