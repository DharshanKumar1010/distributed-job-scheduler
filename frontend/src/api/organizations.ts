import apiClient from './client'
import type { DataResponse, PaginatedResponse, User, UserInviteRequest, UserInviteResponse } from '../types'

export async function listOrgUsers(orgId: string): Promise<User[]> {
  const { data } = await apiClient.get<PaginatedResponse<User>>(`/orgs/${orgId}/users`, {
    params: { page: 1, limit: 100 },
  })
  return data.data
}

export async function inviteUser(
  orgId: string,
  payload: UserInviteRequest,
): Promise<UserInviteResponse> {
  const { data } = await apiClient.post<DataResponse<UserInviteResponse>>(
    `/orgs/${orgId}/users`,
    payload,
  )
  return data.data
}

export async function updateUserRole(orgId: string, userId: string, role: string): Promise<User> {
  const { data } = await apiClient.patch<DataResponse<User>>(`/orgs/${orgId}/users/${userId}`, {
    role,
  })
  return data.data
}

export async function removeUser(orgId: string, userId: string): Promise<User> {
  const { data } = await apiClient.delete<DataResponse<User>>(`/orgs/${orgId}/users/${userId}`)
  return data.data
}
