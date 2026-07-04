import apiClient from './client'
import type { PaginatedResponse, RetryPolicy } from '../types'

export async function listRetryPolicies(): Promise<RetryPolicy[]> {
  const { data } = await apiClient.get<PaginatedResponse<RetryPolicy>>('/retry-policies', {
    params: { page: 1, limit: 100 },
  })
  return data.data
}
