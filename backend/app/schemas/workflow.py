import uuid

from pydantic import BaseModel, Field, model_validator

from app.models.job import JobStatus
from app.models.retry_policy import RetryStrategy


class WorkflowJobSpec(BaseModel):
    ref: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=255)
    queue_id: uuid.UUID
    payload: dict = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)
    priority: int = Field(default=5, ge=0, le=10)
    max_attempts: int = Field(default=3, ge=1)
    retry_strategy: RetryStrategy = RetryStrategy.exponential
    base_delay_seconds: int = Field(default=60, ge=1)
    max_delay_seconds: int = Field(default=3600, ge=1)
    max_runtime_seconds: int = Field(default=300, ge=1)
    tags: list[str] = Field(default_factory=list)


class WorkflowCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    jobs: list[WorkflowJobSpec] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_refs(self) -> "WorkflowCreateRequest":
        ref_ids = {job.ref for job in self.jobs}
        if len(ref_ids) != len(self.jobs):
            raise ValueError("Duplicate job 'ref' values in workflow payload")
        for job in self.jobs:
            for dep_ref in job.depends_on:
                if dep_ref not in ref_ids:
                    raise ValueError(f"depends_on references unknown ref '{dep_ref}'")
                if dep_ref == job.ref:
                    raise ValueError(f"job '{job.ref}' cannot depend on itself")
        return self


class WorkflowJobResult(BaseModel):
    ref: str
    id: uuid.UUID
    name: str
    status: JobStatus


class WorkflowCreateResult(BaseModel):
    name: str
    jobs: list[WorkflowJobResult]
    dependency_map: dict[str, list[str]]
