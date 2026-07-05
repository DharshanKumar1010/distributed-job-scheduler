import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis } from 'recharts'
import { ErrorState } from '../components/ErrorState'
import { LiveFeed } from '../components/LiveFeed'
import { PageHeader } from '../components/PageHeader'
import { PulseRing } from '../components/PulseRing'
import { Skeleton } from '../components/Skeleton'
import { StatCard } from '../components/StatCard'
import { useDashboardStats } from '../hooks/useDashboardStats'
import { useDefaultProject } from '../hooks/useProject'
import { useWebSocket } from '../hooks/useWebSocket'

export function DashboardPage() {
  const { data: project, isLoading: projectLoading, isError: projectError } = useDefaultProject()
  const { stats, isLoading: statsLoading, isError: statsError, refetch } = useDashboardStats(
    project?.id,
  )
  const { status: wsStatus } = useWebSocket()

  const isLoading = projectLoading || statsLoading
  const isError = projectError || statsError
  const isLive = wsStatus === 'connected'

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

      {!isLoading && !isError && (
        <>
          <div className="grid grid-cols-5 gap-4">
            <StatCard label="Jobs Today" value={stats.jobsToday} />
            <StatCard label="Running Now" value={stats.runningNow} />
            <StatCard label="Failed" value={stats.failed} />
            <StatCard label="Workers Online" value={stats.workersOnline} />
            <StatCard
              label="Rate Limited"
              value={stats.rateLimited}
              accentColor="var(--warning)"
            />
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
            <div className="mb-2 flex items-center justify-between">
              <div className="text-xs uppercase tracking-widest text-secondary">Live Feed</div>
              <div className="flex items-center gap-1.5">
                {isLive ? (
                  <>
                    <PulseRing color="success" pulse size={8} />
                    <span className="text-xs" style={{ color: 'var(--accent)' }}>
                      LIVE
                    </span>
                  </>
                ) : (
                  <>
                    <span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: 'var(--text-secondary)' }} />
                    <span className="text-xs text-secondary">OFFLINE</span>
                  </>
                )}
              </div>
            </div>
            <LiveFeed />
          </div>
        </>
      )}
    </div>
  )
}
