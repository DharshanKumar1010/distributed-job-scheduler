import uuid

from pydantic import BaseModel


class ShardWorkerOut(BaseModel):
    worker_id: uuid.UUID
    hostname: str
    current_jobs: int


class ShardOut(BaseModel):
    shard_id: int
    workers: list[ShardWorkerOut]
    pending_jobs: int
    running_jobs: int


class ShardDistributionOut(BaseModel):
    shard_count: int
    shards: list[ShardOut]
    unassigned_jobs: int
    recommendation: str


class RebalanceResult(BaseModel):
    status: str
    expected_completion_seconds: int
