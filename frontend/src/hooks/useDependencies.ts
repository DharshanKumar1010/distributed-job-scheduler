import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  addDependency,
  createWorkflow,
  getJobDependencies,
  getJobDependents,
  removeDependency,
} from '../api/dependencies'

export function useJobDependencies(jobId: string | undefined) {
  return useQuery({
    queryKey: ['job-dependencies', jobId],
    queryFn: () => getJobDependencies(jobId as string),
    enabled: !!jobId,
  })
}

export function useJobDependents(jobId: string | undefined) {
  return useQuery({
    queryKey: ['job-dependents', jobId],
    queryFn: () => getJobDependents(jobId as string),
    enabled: !!jobId,
  })
}

export function useAddDependency(jobId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (dependsOnJobId: string) => addDependency(jobId, dependsOnJobId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['job', jobId] })
      queryClient.invalidateQueries({ queryKey: ['job-dependencies', jobId] })
      queryClient.invalidateQueries({ queryKey: ['job-dependents', jobId] })
    },
  })
}

export function useRemoveDependency(jobId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (depJobId: string) => removeDependency(jobId, depJobId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['job', jobId] })
      queryClient.invalidateQueries({ queryKey: ['job-dependencies', jobId] })
      queryClient.invalidateQueries({ queryKey: ['job-dependents', jobId] })
    },
  })
}

export function useCreateWorkflow() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: createWorkflow,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jobs'] })
    },
  })
}
