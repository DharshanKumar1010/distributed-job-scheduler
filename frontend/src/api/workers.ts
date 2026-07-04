import apiClient from './client'
import type { DataResponse, PaginatedResponse, Worker, WorkerDetail } from '../types'

export async function listWorkers(): Promise<Worker[]> {
  const { data } = await apiClient.get<PaginatedResponse<Worker>>('/workers', {
    params: { page: 1, limit: 100 },
  })
  return data.data
}

export async function getWorker(workerId: string): Promise<WorkerDetail> {
  const { data } = await apiClient.get<DataResponse<WorkerDetail>>(`/workers/${workerId}`)
  return data.data
}

export async function forceOffline(workerId: string): Promise<Worker> {
  const { data } = await apiClient.delete<DataResponse<Worker>>(`/workers/${workerId}`)
  return data.data
}
