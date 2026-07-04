import { useQuery } from '@tanstack/react-query'
import { listRetryPolicies } from '../api/retryPolicies'

export function useRetryPolicies() {
  return useQuery({
    queryKey: ['retry-policies'],
    queryFn: listRetryPolicies,
    staleTime: 60_000,
  })
}
