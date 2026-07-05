import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  getDlqAnalysis,
  getFailurePatterns,
  listDlqEntries,
  reanalyzeDlqEntry,
  type ListDlqParams,
} from '../api/dlq'

export function useDlqEntries(params: ListDlqParams = {}) {
  return useQuery({
    queryKey: ['dlq', params],
    queryFn: () => listDlqEntries(params),
    refetchInterval: 5000,
  })
}

export function useDlqAnalysis(entryId: string | undefined) {
  return useQuery({
    queryKey: ['dlq-analysis', entryId],
    queryFn: () => getDlqAnalysis(entryId as string),
    enabled: !!entryId,
    // Poll while generating so the UI naturally settles once ai_summary
    // lands, even if the WS event is missed for some reason.
    refetchInterval: (query) => (query.state.data?.is_generating ? 2000 : false),
  })
}

export function useReanalyzeDlqEntry(entryId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => reanalyzeDlqEntry(entryId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['dlq-analysis', entryId] })
      queryClient.invalidateQueries({ queryKey: ['dlq'] })
    },
  })
}

export function useFailurePatterns(queueId: string | undefined) {
  return useQuery({
    queryKey: ['failure-patterns', queueId],
    queryFn: () => getFailurePatterns(queueId as string),
    enabled: !!queueId,
  })
}
