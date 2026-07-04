import { useQuery } from '@tanstack/react-query'
import { getQueue, listQueues } from '../api/queues'

export function useQueues(projectId: string | undefined) {
  return useQuery({
    queryKey: ['queues', projectId],
    queryFn: () => listQueues(projectId as string),
    enabled: !!projectId,
    refetchInterval: 5000,
  })
}

export function useQueue(projectId: string | undefined, queueId: string | undefined) {
  return useQuery({
    // Keyed by queueId alone (not [queue, projectId, queueId]) so WebSocket
    // queue.stats events — which only know queue_id — can patch this cache
    // entry directly via setQueryData(['queue', queueId], ...).
    queryKey: ['queue', queueId],
    queryFn: () => getQueue(projectId as string, queueId as string),
    enabled: !!projectId && !!queueId,
    refetchInterval: 5000,
  })
}
