import apiClient from './client'
import type { DataResponse, PaginatedResponse, Project } from '../types'

export async function listProjects(orgId: string): Promise<Project[]> {
  const { data } = await apiClient.get<PaginatedResponse<Project>>(`/orgs/${orgId}/projects`, {
    params: { page: 1, limit: 50 },
  })
  return data.data
}

export async function createProject(
  orgId: string,
  payload: { name: string; slug: string; description?: string },
): Promise<Project> {
  const { data } = await apiClient.post<DataResponse<Project>>(`/orgs/${orgId}/projects`, payload)
  return data.data
}
