import { useQuery } from '@tanstack/react-query'
import { getWorker, listWorkers } from '../api/workers'

export function useWorkers() {
  return useQuery({
    queryKey: ['workers'],
    queryFn: listWorkers,
    refetchInterval: 5000,
  })
}

export function useWorker(workerId: string | undefined) {
  return useQuery({
    queryKey: ['worker', workerId],
    queryFn: () => getWorker(workerId as string),
    enabled: !!workerId,
    refetchInterval: 5000,
  })
}
