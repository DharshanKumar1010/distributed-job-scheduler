import { useQuery } from '@tanstack/react-query'
import { listDlqEntries, type ListDlqParams } from '../api/dlq'

export function useDlqEntries(params: ListDlqParams = {}) {
  return useQuery({
    queryKey: ['dlq', params],
    queryFn: () => listDlqEntries(params),
    refetchInterval: 5000,
  })
}
