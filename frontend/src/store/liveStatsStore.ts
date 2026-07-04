import { create } from 'zustand'
import type { Queue, Worker, WorkerStatus } from '../types'

export interface ChartPoint {
  minute: string
  completed: number
}

interface QueueStatsSnapshot {
  pending_count: number
  running_count: number
  failed_count: number
}

interface LiveStatsState {
  queueStatsById: Record<string, QueueStatsSnapshot>
  workerStatusById: Record<string, WorkerStatus>
  jobsToday: number
  chartData: ChartPoint[]
  seeded: boolean
  seedQueues: (queues: Queue[]) => void
  seedWorkers: (workers: Worker[]) => void
  seedJobsToday: (count: number) => void
  seedChartData: (points: ChartPoint[]) => void
  patchQueueStats: (queueId: string, stats: QueueStatsSnapshot) => void
  setWorkerStatus: (workerId: string, status: WorkerStatus) => void
  incrementCurrentMinuteBucket: () => void
}

export const useLiveStatsStore = create<LiveStatsState>()((set) => ({
  queueStatsById: {},
  workerStatusById: {},
  jobsToday: 0,
  chartData: [],
  seeded: false,
  seedQueues: (queues) =>
    set({
      queueStatsById: Object.fromEntries(
        queues.map((q) => [
          q.id,
          {
            pending_count: q.stats.pending_count,
            running_count: q.stats.running_count,
            failed_count: q.stats.failed_count,
          },
        ]),
      ),
      seeded: true,
    }),
  seedWorkers: (workers) =>
    set({ workerStatusById: Object.fromEntries(workers.map((w) => [w.id, w.status])) }),
  seedJobsToday: (count) => set({ jobsToday: count }),
  seedChartData: (points) => set({ chartData: points }),
  patchQueueStats: (queueId, stats) =>
    set((state) => ({ queueStatsById: { ...state.queueStatsById, [queueId]: stats } })),
  setWorkerStatus: (workerId, status) =>
    set((state) => ({ workerStatusById: { ...state.workerStatusById, [workerId]: status } })),
  incrementCurrentMinuteBucket: () =>
    set((state) => {
      if (state.chartData.length === 0) return state
      const next = [...state.chartData]
      next[next.length - 1] = {
        ...next[next.length - 1],
        completed: next[next.length - 1].completed + 1,
      }
      return { chartData: next }
    }),
}))

export function selectRunningNow(state: LiveStatsState): number {
  return Object.values(state.queueStatsById).reduce((sum, s) => sum + s.running_count, 0)
}

export function selectFailed(state: LiveStatsState): number {
  return Object.values(state.queueStatsById).reduce((sum, s) => sum + s.failed_count, 0)
}

export function selectWorkersOnline(state: LiveStatsState): number {
  return Object.values(state.workerStatusById).filter((status) => status !== 'offline').length
}
