import apiClient from './client'
import type {
  DataResponse,
  Job,
  JobCreateRequest,
  JobDetail,
  JobLog,
  JobStatus,
  JobType,
  PaginatedResponse,
} from '../types'

export interface ListJobsParams {
  status?: JobStatus
  job_type?: JobType
  tag?: string
  page?: number
  limit?: number
  sort?: 'created_at' | 'priority'
}

export async function listJobs(
  queueId: string,
  params: ListJobsParams = {},
): Promise<PaginatedResponse<Job>> {
  const { data } = await apiClient.get<PaginatedResponse<Job>>(`/queues/${queueId}/jobs`, {
    params,
  })
  return data
}

export async function createJob(queueId: string, payload: JobCreateRequest): Promise<Job> {
  const { data } = await apiClient.post<DataResponse<Job>>(`/queues/${queueId}/jobs`, payload)
  return data.data
}

export async function getJob(jobId: string): Promise<JobDetail> {
  const { data } = await apiClient.get<DataResponse<JobDetail>>(`/jobs/${jobId}`)
  return data.data
}

export async function cancelJob(jobId: string): Promise<Job> {
  const { data } = await apiClient.delete<DataResponse<Job>>(`/jobs/${jobId}`)
  return data.data
}

export async function retryJob(jobId: string): Promise<Job> {
  const { data } = await apiClient.post<DataResponse<Job>>(`/jobs/${jobId}/retry`)
  return data.data
}

export async function getJobLogs(
  jobId: string,
  page = 1,
  limit = 50,
): Promise<PaginatedResponse<JobLog>> {
  const { data } = await apiClient.get<PaginatedResponse<JobLog>>(`/jobs/${jobId}/logs`, {
    params: { page, limit },
  })
  return data
}

export async function batchCancelJobs(
  jobIds: string[],
): Promise<{ cancelled: string[]; skipped: string[]; not_found: string[] }> {
  const { data } = await apiClient.post<
    DataResponse<{ cancelled: string[]; skipped: string[]; not_found: string[] }>
  >('/jobs/batch-cancel', { job_ids: jobIds })
  return data.data
}
