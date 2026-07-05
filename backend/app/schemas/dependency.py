import uuid

from pydantic import BaseModel, Field

from app.models.job import JobStatus


class WorkflowStatusOut(BaseModel):
    total: int
    completed: int
    running: int
    blocked: int
    failed: int
    dead: int
    queued: int
    progress_pct: float


class DependencyNode(BaseModel):
    job_id: uuid.UUID
    name: str
    status: JobStatus
    depends_on: list["DependencyNode"] = Field(default_factory=list)
    dependents: list["DependencyNode"] = Field(default_factory=list)


class DependencyGraphOut(DependencyNode):
    workflow_status: WorkflowStatusOut


class DependentOut(BaseModel):
    job_id: uuid.UUID
    name: str
    status: JobStatus
    queue_id: uuid.UUID
    blocked_on_others: bool


class AddDependencyRequest(BaseModel):
    depends_on_job_id: uuid.UUID
