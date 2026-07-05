import uuid

from pydantic import BaseModel


class ExecutionPatternOut(BaseModel):
    attempts: int
    avg_duration_ms: float | None
    min_duration_ms: int | None
    max_duration_ms: int | None
    failed_consistently: bool


class DlqAnalysisOut(BaseModel):
    dlq_id: uuid.UUID
    job_name: str
    error_type: str
    ai_summary: str | None
    is_generating: bool
    total_attempts: int
    time_to_failure_ms: int
    execution_pattern: ExecutionPatternOut


class FailurePatternOut(BaseModel):
    total_failures: int
    error_type_distribution: dict[str, int]
    most_common_error: str
    failure_rate_trend: str
    peak_failure_hour: int | None
    recommendation: str
