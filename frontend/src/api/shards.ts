import apiClient from './client'
import type { DataResponse, RebalanceResult, ShardDistribution } from '../types'

export async function getShardDistribution(queueId: string): Promise<ShardDistribution> {
  const { data } = await apiClient.get<DataResponse<ShardDistribution>>(
    `/queues/${queueId}/shards`,
  )
  return data.data
}

export async function rebalanceShards(queueId: string): Promise<RebalanceResult> {
  const { data } = await apiClient.post<DataResponse<RebalanceResult>>(
    `/queues/${queueId}/shards/rebalance`,
  )
  return data.data
}
