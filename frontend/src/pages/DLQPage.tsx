import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { replayDlqEntry, resolveDlqEntry } from '../api/dlq'
import { AiSummaryCard } from '../components/AiSummaryCard'
import { ErrorState } from '../components/ErrorState'
import { PageHeader } from '../components/PageHeader'
import { Skeleton } from '../components/Skeleton'
import { StatusBadge } from '../components/StatusBadge'
import { useDlqAnalysis, useDlqEntries, useFailurePatterns, useReanalyzeDlqEntry } from '../hooks/useDlq'
import { useDefaultProject } from '../hooks/useProject'
import { usePermissions } from '../hooks/usePermissions'
import { useQueues } from '../hooks/useQueue'
import { formatDateTime, truncateId } from '../lib/format'
import type { DeadLetterQueueEntry } from '../types'

const ERROR_TYPE_COLORS: Record<string, string> = {
  'Network/Infrastructure': '#3B82F6',
  Authorization: '#F59E0B',
  'Data/Logic': '#EAB308',
  'Code Bug': '#EF4444',
  'Rate Limiting': '#A855F7',
  'Resource Exhaustion': '#EC4899',
  'Data Conflict': '#14B8A6',
  Unknown: '#94A3B8',
}

function errorTypeColor(errorType: string): string {
  return ERROR_TYPE_COLORS[errorType] ?? ERROR_TYPE_COLORS.Unknown
}

function truncate(text: string, length: number): string {
  return text.length > length ? `${text.slice(0, length)}…` : text
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  const seconds = ms / 1000
  if (seconds < 60) return `${seconds.toFixed(1)}s`
  const minutes = seconds / 60
  return `${minutes.toFixed(1)}m`
}

function FailurePatternChart({ queueId }: { queueId: string | undefined }) {
  const { data: pattern, isLoading } = useFailurePatterns(queueId)

  if (!queueId) return null
  if (isLoading || !pattern) {
    return (
      <div className="mb-6 rounded-lg border border-border bg-card p-5">
        <Skeleton rows={3} />
      </div>
    )
  }

  if (pattern.total_failures === 0) {
    return null
  }

  const entries = Object.entries(pattern.error_type_distribution).sort((a, b) => b[1] - a[1])
  const maxCount = Math.max(...entries.map(([, count]) => count), 1)
  const peakHour = pattern.peak_failure_hour
  const peakHourLabel =
    peakHour != null
      ? `${peakHour % 12 === 0 ? 12 : peakHour % 12}${peakHour < 12 ? 'AM' : 'PM'} UTC`
      : 'n/a'

  return (
    <div className="mb-6 rounded-lg border border-border bg-card p-5">
      <div className="mb-4 flex items-center justify-between">
        <div className="text-xs uppercase tracking-widest text-secondary">
          Failure Pattern ({pattern.total_failures} recent failures)
        </div>
        <span className="text-xs text-secondary">
          Trend: <span className="text-primary">{pattern.failure_rate_trend}</span>
        </span>
      </div>

      <div className="space-y-2">
        {entries.map(([errorType, count]) => (
          <div key={errorType} className="flex items-center gap-3">
            <div className="w-40 shrink-0 truncate text-xs text-secondary">{errorType}</div>
            <div className="h-4 flex-1 overflow-hidden rounded-full bg-elevated">
              <div
                className="h-full rounded-full transition-all duration-300"
                style={{
                  width: `${(count / maxCount) * 100}%`,
                  backgroundColor: errorTypeColor(errorType),
                }}
              />
            </div>
            <div className="w-8 shrink-0 text-right text-xs text-primary">{count}</div>
          </div>
        ))}
      </div>

      <div className="mt-3 text-xs text-secondary">Peak failure hour: {peakHourLabel}</div>
      <div className="mt-2 text-sm" style={{ color: 'var(--accent)' }}>
        {pattern.recommendation}
      </div>
    </div>
  )
}

function ErrorOverview({ entry, errorType }: { entry: DeadLetterQueueEntry; errorType: string }) {
  const { data: analysis } = useDlqAnalysis(entry.id)
  const [expanded, setExpanded] = useState(false)

  return (
    <div className="grid grid-cols-2 gap-6">
      <div>
        <span
          className="inline-flex rounded-full px-2.5 py-0.5 text-xs font-medium"
          style={{ backgroundColor: `${errorTypeColor(errorType)}26`, color: errorTypeColor(errorType) }}
        >
          {errorType}
        </span>
        <div className="mt-3 text-xs text-secondary">
          Attempts <span className="text-primary">{entry.total_attempts}</span>
        </div>
        {analysis && (
          <div className="mt-1 text-xs text-secondary">
            Time to failure{' '}
            <span className="text-primary">{formatDuration(analysis.time_to_failure_ms)}</span>
          </div>
        )}
      </div>
      <div>
        <div className="mb-1 text-xs uppercase tracking-wide text-secondary">Last error</div>
        <pre
          className={`overflow-y-auto whitespace-pre-wrap rounded-md bg-base p-3 font-mono text-xs text-danger ${
            expanded ? '' : 'max-h-24'
          }`}
        >
          {entry.last_error}
        </pre>
        {entry.last_error.split('\n').length > 4 && (
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="mt-1 text-xs text-accent hover:underline"
          >
            {expanded ? 'Show less' : 'Show more'}
          </button>
        )}
      </div>
    </div>
  )
}

function DlqRow({
  entry,
  queueName,
  isOpen,
  onToggle,
}: {
  entry: DeadLetterQueueEntry
  queueName?: string
  isOpen: boolean
  onToggle: () => void
}) {
  const queryClient = useQueryClient()
  const { can } = usePermissions()
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['dlq'] })

  const resolveMutation = useMutation({ mutationFn: () => resolveDlqEntry(entry.id), onSuccess: invalidate })
  const replayMutation = useMutation({ mutationFn: () => replayDlqEntry(entry.id), onSuccess: invalidate })
  const reanalyzeMutation = useReanalyzeDlqEntry(entry.id)
  const { data: analysis } = useDlqAnalysis(isOpen ? entry.id : undefined)

  return (
    <>
      <tr
        className="cursor-pointer border-t border-border transition-colors hover:bg-elevated"
        onClick={onToggle}
      >
        <td className="px-4 py-3">
          <div className="flex items-center gap-2 text-primary">
            {isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
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
      {isOpen && (
        <tr className="border-t border-border">
          <td colSpan={7} className="bg-base/40 px-4 py-5">
            <div className="space-y-5">
              <ErrorOverview entry={entry} errorType={analysis?.error_type ?? 'Unknown'} />
              <AiSummaryCard
                summary={analysis?.ai_summary ?? null}
                isGenerating={analysis?.is_generating ?? true}
                onReanalyze={can('dlq:resolve') ? () => reanalyzeMutation.mutate() : undefined}
                reanalyzing={reanalyzeMutation.isPending}
              />
            </div>
          </td>
        </tr>
      )}
    </>
  )
}

export function DLQPage() {
  const [searchParams] = useSearchParams()
  const { data: project } = useDefaultProject()
  const { data: queues } = useQueues(project?.id)
  const { data: result, isLoading, isError, refetch } = useDlqEntries({ limit: 50 })
  const [patternQueueId, setPatternQueueId] = useState<string | undefined>(undefined)
  const [expandedId, setExpandedId] = useState<string | null>(searchParams.get('expand'))

  useEffect(() => {
    const fromUrl = searchParams.get('expand')
    if (fromUrl) setExpandedId(fromUrl)
  }, [searchParams])

  const queueNameById = new Map((queues ?? []).map((q) => [q.id, q.name]))
  const activePatternQueueId = patternQueueId ?? queues?.[0]?.id

  return (
    <div>
      <PageHeader title="Dead Letter Queue" description="Jobs that exhausted all retry attempts" />

      {(queues?.length ?? 0) > 0 && (
        <div className="mb-3 flex items-center gap-2">
          <label className="text-xs text-secondary">Failure pattern for</label>
          <select
            value={activePatternQueueId ?? ''}
            onChange={(e) => setPatternQueueId(e.target.value)}
            className="rounded-md border border-border bg-card px-2 py-1 text-xs text-primary"
          >
            {(queues ?? []).map((q) => (
              <option key={q.id} value={q.id}>
                {q.name}
              </option>
            ))}
          </select>
        </div>
      )}
      <FailurePatternChart queueId={activePatternQueueId} />

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
                <DlqRow
                  key={entry.id}
                  entry={entry}
                  queueName={queueNameById.get(entry.queue_id)}
                  isOpen={expandedId === entry.id}
                  onToggle={() => setExpandedId((cur) => (cur === entry.id ? null : entry.id))}
                />
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
