import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis } from 'recharts'
import { ErrorState } from '../components/ErrorState'
import { PageHeader } from '../components/PageHeader'
import { Skeleton } from '../components/Skeleton'
import { StatCard } from '../components/StatCard'
import { StatusBadge } from '../components/StatusBadge'
import { useDashboardStats } from '../hooks/useDashboardStats'
import { useDefaultProject } from '../hooks/useProject'
import { formatTimestamp } from '../lib/format'

export function DashboardPage() {
  const { data: project, isLoading: projectLoading, isError: projectError } = useDefaultProject()
  const {
    data: stats,
    isLoading: statsLoading,
    isError: statsError,
    refetch,
  } = useDashboardStats(project?.id)

  const isLoading = projectLoading || statsLoading
  const isError = projectError || statsError

  return (
    <div>
      <PageHeader title="Dashboard" description="Overview of your job scheduling activity" />

      {isLoading && (
        <div className="rounded-lg border border-border bg-card p-6">
          <Skeleton rows={3} />
        </div>
      )}

      {!isLoading && isError && (
        <ErrorState message="Couldn't load dashboard data" onRetry={() => refetch()} />
      )}

      {!isLoading && !isError && stats && (
        <>
          <div className="grid grid-cols-4 gap-4">
            <StatCard label="Jobs Today" value={stats.jobsToday} />
            <StatCard label="Running Now" value={stats.runningNow} />
            <StatCard label="Failed" value={stats.failed} />
            <StatCard label="Workers Online" value={stats.workersOnline} />
          </div>

          <div className="mt-6 rounded-lg border border-border bg-card p-5">
            <div className="mb-4 text-xs uppercase tracking-widest text-secondary">
              Jobs Completed / Minute (last 60 min)
            </div>
            <ResponsiveContainer width="100%" height={220}>
              <AreaChart data={stats.chartData}>
                <defs>
                  <linearGradient id="completedGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.3} />
                    <stop offset="100%" stopColor="var(--accent)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis
                  dataKey="minute"
                  axisLine={{ stroke: 'var(--border)' }}
                  tickLine={false}
                  tick={{ fill: 'var(--text-secondary)', fontSize: 11 }}
                  interval={9}
                />
                <Tooltip
                  contentStyle={{
                    background: 'var(--bg-elevated)',
                    border: '1px solid var(--border)',
                    borderRadius: 8,
                    fontSize: 12,
                  }}
                  labelStyle={{ color: 'var(--text-secondary)' }}
                  itemStyle={{ color: 'var(--text-primary)' }}
                />
                <Area
                  type="monotone"
                  dataKey="completed"
                  stroke="var(--accent)"
                  strokeWidth={2}
                  fill="url(#completedGradient)"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>

          <div className="mt-6 rounded-lg border border-border bg-card p-5">
            <div className="mb-2 text-xs uppercase tracking-widest text-secondary">Live Feed</div>
            {stats.recentJobs.length === 0 && (
              <p className="py-6 text-center text-sm text-secondary">No recent activity</p>
            )}
            <div>
              {stats.recentJobs.map((job) => (
                <div
                  key={job.id}
                  className="flex items-center justify-between border-t border-border py-2.5 first:border-t-0"
                >
                  <span className="truncate text-sm text-primary">{job.name}</span>
                  <div className="flex shrink-0 items-center gap-3">
                    <span className="font-mono text-xs text-secondary">
                      {formatTimestamp(job.updated_at)}
                    </span>
                    <StatusBadge status={job.status} />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
