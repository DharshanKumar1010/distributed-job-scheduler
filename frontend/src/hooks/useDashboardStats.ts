import { useQuery } from '@tanstack/react-query'
import { useEffect } from 'react'
import { listJobs } from '../api/jobs'
import { listQueues } from '../api/queues'
import { listWorkers } from '../api/workers'
import {
  selectFailed,
  selectRunningNow,
  selectWorkersOnline,
  useLiveStatsStore,
  type ChartPoint,
} from '../store/liveStatsStore'
import type { Job } from '../types'

export interface DashboardStats {
  jobsToday: number
  runningNow: number
  failed: number
  workersOnline: number
  chartData: ChartPoint[]
}

/** Buckets completed jobs into 60 one-minute buckets covering the last hour. */
function bucketCompletedPerMinute(jobs: Job[]): ChartPoint[] {
  const now = Date.now()
  const counts = new Array<number>(60).fill(0)

  for (const job of jobs) {
    if (!job.completed_at) continue
    const minutesAgo = Math.floor((now - new Date(job.completed_at).getTime()) / 60_000)
    if (minutesAgo >= 0 && minutesAgo < 60) {
      counts[59 - minutesAgo] += 1
    }
  }

  return counts.map((completed, index) => {
    const ts = new Date(now - (59 - index) * 60_000)
    return {
      minute: ts.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      completed,
    }
  })
}

/**
 * Seeds live-stats baseline data once (no polling — see CLAUDE.md's Phase 7
 * note that these numbers should update from WebSocket events, not polling),
 * then reads the ever-fresh numbers back out of useLiveStatsStore, which the
 * WebSocket handler patches directly as job/worker/queue events arrive.
 */
export function useDashboardStats(projectId: string | undefined) {
  const seedQueues = useLiveStatsStore((s) => s.seedQueues)
  const seedWorkers = useLiveStatsStore((s) => s.seedWorkers)
  const seedJobsToday = useLiveStatsStore((s) => s.seedJobsToday)
  const seedChartData = useLiveStatsStore((s) => s.seedChartData)
  const runningNow = useLiveStatsStore(selectRunningNow)
  const failed = useLiveStatsStore(selectFailed)
  const workersOnline = useLiveStatsStore(selectWorkersOnline)
  const jobsToday = useLiveStatsStore((s) => s.jobsToday)
  const chartData = useLiveStatsStore((s) => s.chartData)

  const baseline = useQuery({
    queryKey: ['dashboard-baseline', projectId],
    queryFn: async () => {
      const [queues, workers] = await Promise.all([
        listQueues(projectId as string),
        listWorkers(),
      ])

      const jobLists = await Promise.all(
        queues.map((q) => listJobs(q.id, { limit: 100, sort: 'created_at' })),
      )
      const allJobs = jobLists.flatMap((r) => r.data)

      const startOfToday = new Date()
      startOfToday.setHours(0, 0, 0, 0)
      const jobsToday = allJobs.filter(
        (j) => new Date(j.created_at).getTime() >= startOfToday.getTime(),
      ).length

      const chartData = bucketCompletedPerMinute(allJobs.filter((j) => j.status === 'completed'))

      return { queues, workers, jobsToday, chartData }
    },
    enabled: !!projectId,
    staleTime: Infinity, // fetched once as a baseline; WebSocket events keep it fresh from here
    refetchOnWindowFocus: false,
  })

  useEffect(() => {
    if (!baseline.data) return
    seedQueues(baseline.data.queues)
    seedWorkers(baseline.data.workers)
    seedJobsToday(baseline.data.jobsToday)
    seedChartData(baseline.data.chartData)
  }, [baseline.data, seedQueues, seedWorkers, seedJobsToday, seedChartData])

  const stats: DashboardStats = { jobsToday, runningNow, failed, workersOnline, chartData }

  return {
    stats,
    isLoading: baseline.isLoading,
    isError: baseline.isError,
    refetch: baseline.refetch,
  }
}
