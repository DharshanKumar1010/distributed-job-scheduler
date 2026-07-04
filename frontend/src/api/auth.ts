import apiClient from './client'
import type { DataResponse, TokenResponse, User } from '../types'

export interface LoginRequest {
  email: string
  password: string
}

export interface RegisterRequest {
  org_name: string
  org_slug: string
  email: string
  password: string
  full_name?: string
}

export async function login(payload: LoginRequest): Promise<TokenResponse> {
  const { data } = await apiClient.post<DataResponse<TokenResponse>>('/auth/login', payload)
  return data.data
}

export async function register(payload: RegisterRequest): Promise<TokenResponse> {
  const { data } = await apiClient.post<DataResponse<TokenResponse>>('/auth/register', payload)
  return data.data
}

export async function fetchMe(): Promise<User> {
  const { data } = await apiClient.get<DataResponse<User>>('/auth/me')
  return data.data
}
