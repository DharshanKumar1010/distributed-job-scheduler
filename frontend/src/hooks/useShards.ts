import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getShardDistribution, rebalanceShards } from '../api/shards'

export function useShardDistribution(queueId: string | undefined) {
  return useQuery({
    queryKey: ['shard-distribution', queueId],
    queryFn: () => getShardDistribution(queueId as string),
    enabled: !!queueId,
    refetchInterval: 5000,
  })
}

export function useRebalanceShards(queueId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => rebalanceShards(queueId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['shard-distribution', queueId] })
    },
  })
}
