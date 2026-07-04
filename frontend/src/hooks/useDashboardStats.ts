import { useQuery } from '@tanstack/react-query'
import { listJobs } from '../api/jobs'
import { listQueues } from '../api/queues'
import { listWorkers } from '../api/workers'
import type { Job } from '../types'

export interface ChartPoint {
  minute: string
  completed: number
}

export interface DashboardStats {
  jobsToday: number
  runningNow: number
  failed: number
  workersOnline: number
  chartData: ChartPoint[]
  recentJobs: Job[]
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

export function useDashboardStats(projectId: string | undefined) {
  return useQuery({
    queryKey: ['dashboard-stats', projectId],
    queryFn: async (): Promise<DashboardStats> => {
      const [queues, workers] = await Promise.all([
        listQueues(projectId as string),
        listWorkers(),
      ])

      const runningNow = queues.reduce((sum, q) => sum + q.stats.running_count, 0)
      const failed = queues.reduce((sum, q) => sum + q.stats.failed_count, 0)
      const workersOnline = workers.filter((w) => w.status !== 'offline').length

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

      const recentJobs = [...allJobs]
        .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())
        .slice(0, 20)

      return { jobsToday, runningNow, failed, workersOnline, chartData, recentJobs }
    },
    enabled: !!projectId,
    refetchInterval: 5000,
  })
}
