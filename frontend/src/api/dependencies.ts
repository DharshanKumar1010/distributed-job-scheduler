import apiClient from './client'
import type {
  DataResponse,
  DependencyGraph,
  DependentJob,
  Job,
  WorkflowCreateRequest,
  WorkflowCreateResult,
} from '../types'

export async function getJobDependencies(jobId: string): Promise<DependencyGraph> {
  const { data } = await apiClient.get<DataResponse<DependencyGraph>>(
    `/jobs/${jobId}/dependencies`,
  )
  return data.data
}

export async function getJobDependents(jobId: string): Promise<DependentJob[]> {
  const { data } = await apiClient.get<DataResponse<DependentJob[]>>(`/jobs/${jobId}/dependents`)
  return data.data
}

export async function addDependency(jobId: string, dependsOnJobId: string): Promise<Job> {
  const { data } = await apiClient.post<DataResponse<Job>>(`/jobs/${jobId}/dependencies`, {
    depends_on_job_id: dependsOnJobId,
  })
  return data.data
}

export async function removeDependency(jobId: string, depJobId: string): Promise<Job> {
  const { data } = await apiClient.delete<DataResponse<Job>>(
    `/jobs/${jobId}/dependencies/${depJobId}`,
  )
  return data.data
}

export async function createWorkflow(
  payload: WorkflowCreateRequest,
): Promise<WorkflowCreateResult> {
  const { data } = await apiClient.post<DataResponse<WorkflowCreateResult>>('/workflows', payload)
  return data.data
}
