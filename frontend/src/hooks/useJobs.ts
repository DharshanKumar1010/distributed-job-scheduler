import { useQuery } from '@tanstack/react-query'
import { getJob, getJobLogs, listJobs, type ListJobsParams } from '../api/jobs'

export function useJobs(queueId: string | undefined, params: ListJobsParams = {}) {
  return useQuery({
    queryKey: ['jobs', queueId, params],
    queryFn: () => listJobs(queueId as string, params),
    enabled: !!queueId,
    refetchInterval: 5000,
  })
}

export function useJob(jobId: string | undefined) {
  return useQuery({
    queryKey: ['job', jobId],
    queryFn: () => getJob(jobId as string),
    enabled: !!jobId,
    refetchInterval: 5000,
  })
}

export function useJobLogs(jobId: string | undefined, page = 1, limit = 50) {
  return useQuery({
    queryKey: ['job-logs', jobId, page, limit],
    queryFn: () => getJobLogs(jobId as string, page, limit),
    enabled: !!jobId,
    refetchInterval: 5000,
  })
}
