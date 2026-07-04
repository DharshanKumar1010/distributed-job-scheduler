import apiClient from './client'
import type { DataResponse, PaginatedResponse, Queue } from '../types'

export async function listQueues(projectId: string): Promise<Queue[]> {
  const { data } = await apiClient.get<PaginatedResponse<Queue>>(
    `/projects/${projectId}/queues`,
    { params: { page: 1, limit: 100 } },
  )
  return data.data
}

export async function getQueue(projectId: string, queueId: string): Promise<Queue> {
  const { data } = await apiClient.get<DataResponse<Queue>>(
    `/projects/${projectId}/queues/${queueId}`,
  )
  return data.data
}

export interface QueueUpdatePayload {
  name?: string
  description?: string | null
  priority?: number
  concurrency_limit?: number
  retry_policy_id?: string | null
}

export async function updateQueue(
  projectId: string,
  queueId: string,
  payload: QueueUpdatePayload,
): Promise<Queue> {
  const { data } = await apiClient.patch<DataResponse<Queue>>(
    `/projects/${projectId}/queues/${queueId}`,
    payload,
  )
  return data.data
}

export async function pauseQueue(projectId: string, queueId: string): Promise<Queue> {
  const { data } = await apiClient.post<DataResponse<Queue>>(
    `/projects/${projectId}/queues/${queueId}/pause`,
  )
  return data.data
}

export async function resumeQueue(projectId: string, queueId: string): Promise<Queue> {
  const { data } = await apiClient.post<DataResponse<Queue>>(
    `/projects/${projectId}/queues/${queueId}/resume`,
  )
  return data.data
}
