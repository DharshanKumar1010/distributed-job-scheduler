import apiClient from './client'
import type {
  DataResponse,
  DeadLetterQueueEntry,
  DlqAnalysis,
  FailurePattern,
  Job,
  PaginatedResponse,
} from '../types'

export interface ListDlqParams {
  queue_id?: string
  job_id?: string
  is_resolved?: boolean
  page?: number
  limit?: number
}

export async function listDlqEntries(
  params: ListDlqParams = {},
): Promise<PaginatedResponse<DeadLetterQueueEntry>> {
  const { data } = await apiClient.get<PaginatedResponse<DeadLetterQueueEntry>>(
    '/dead-letter-queue',
    { params },
  )
  return data
}

export async function resolveDlqEntry(entryId: string): Promise<DeadLetterQueueEntry> {
  const { data } = await apiClient.post<DataResponse<DeadLetterQueueEntry>>(
    `/dead-letter-queue/${entryId}/resolve`,
  )
  return data.data
}

export async function replayDlqEntry(entryId: string): Promise<Job> {
  const { data } = await apiClient.post<DataResponse<Job>>(
    `/dead-letter-queue/${entryId}/replay`,
  )
  return data.data
}

export async function getDlqAnalysis(entryId: string): Promise<DlqAnalysis> {
  const { data } = await apiClient.get<DataResponse<DlqAnalysis>>(
    `/dead-letter-queue/${entryId}/analysis`,
  )
  return data.data
}

export async function reanalyzeDlqEntry(entryId: string): Promise<{ status: string }> {
  const { data } = await apiClient.post<DataResponse<{ status: string }>>(
    `/dead-letter-queue/${entryId}/reanalyze`,
  )
  return data.data
}

export async function getFailurePatterns(queueId: string): Promise<FailurePattern> {
  const { data } = await apiClient.get<DataResponse<FailurePattern>>(
    `/queues/${queueId}/failure-patterns`,
  )
  return data.data
}
