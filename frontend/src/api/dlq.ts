import apiClient from './client'
import type { DataResponse, DeadLetterQueueEntry, Job, PaginatedResponse } from '../types'

export interface ListDlqParams {
  queue_id?: string
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
