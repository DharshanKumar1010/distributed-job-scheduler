import { useQuery } from '@tanstack/react-query'
import { getWorker, listWorkers } from '../api/workers'

// No refetchInterval — worker.heartbeat WebSocket events patch these caches
// directly (see useWebSocket.ts), so polling would just be redundant.
export function useWorkers() {
  return useQuery({
    queryKey: ['workers'],
    queryFn: listWorkers,
  })
}

export function useWorker(workerId: string | undefined) {
  return useQuery({
    queryKey: ['worker', workerId],
    queryFn: () => getWorker(workerId as string),
    enabled: !!workerId,
  })
}
