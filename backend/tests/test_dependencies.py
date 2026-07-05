import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update

from app.database import AsyncSessionLocal
from app.models.job import Job, JobStatus, JobType
from app.models.job_dependency import JobDependency
from app.schemas.workflow import WorkflowCreateRequest, WorkflowJobSpec
from app.services import dependency_service, job_service


async def _create_job(queue_id: uuid.UUID, **overrides) -> Job:
    defaults = dict(
        queue_id=queue_id,
        name="test-job",
        payload={},
        status=JobStatus.queued,
        job_type=JobType.immediate,
        max_attempts=3,
        retry_strategy="fixed",
        base_delay_seconds=0,
        max_delay_seconds=60,
    )
    defaults.update(overrides)
    async with AsyncSessionLocal() as db:
        job = Job(**defaults)
        db.add(job)
        await db.commit()
        await db.refresh(job)
        return job


async def _link(job_id: uuid.UUID, depends_on_job_id: uuid.UUID) -> None:
    async with AsyncSessionLocal() as db:
        db.add(JobDependency(job_id=job_id, depends_on_job_id=depends_on_job_id))
        await db.commit()


async def _complete(job_id: uuid.UUID) -> None:
    """Simulates a worker finishing a job successfully."""
    async with AsyncSessionLocal() as db:
        await db.execute(
            update(Job)
            .where(Job.id == job_id)
            .values(status=JobStatus.completed, completed_at=datetime.now(timezone.utc))
        )
        await db.commit()


async def _status_of(job_id: uuid.UUID) -> JobStatus:
    async with AsyncSessionLocal() as db:
        job = await db.get(Job, job_id)
        return job.status


async def _complete_and_unblock(job_id: uuid.UUID, org_id: uuid.UUID) -> list[uuid.UUID]:
    await _complete(job_id)
    async with AsyncSessionLocal() as db:
        return await dependency_service.check_and_unblock(job_id, db, None, org_id)


async def test_linear_chain_unblocks_sequentially(test_org_queue):
    org_id, queue_id = test_org_queue

    job_a = await _create_job(queue_id, name="A")
    job_b = await _create_job(queue_id, name="B", status=JobStatus.blocked)
    job_c = await _create_job(queue_id, name="C", status=JobStatus.blocked)
    await _link(job_b.id, job_a.id)
    await _link(job_c.id, job_b.id)

    await _complete_and_unblock(job_a.id, org_id)
    assert await _status_of(job_b.id) == JobStatus.queued
    assert await _status_of(job_c.id) == JobStatus.blocked

    await _complete_and_unblock(job_b.id, org_id)
    assert await _status_of(job_c.id) == JobStatus.queued


async def test_fan_in_stays_blocked_until_all_complete(test_org_queue):
    org_id, queue_id = test_org_queue

    job_a = await _create_job(queue_id, name="A")
    job_b = await _create_job(queue_id, name="B")
    job_c = await _create_job(queue_id, name="C", status=JobStatus.blocked)
    await _link(job_c.id, job_a.id)
    await _link(job_c.id, job_b.id)

    await _complete_and_unblock(job_a.id, org_id)
    assert await _status_of(job_c.id) == JobStatus.blocked

    await _complete_and_unblock(job_b.id, org_id)
    assert await _status_of(job_c.id) == JobStatus.queued


async def test_fan_out_unblocks_both_simultaneously(test_org_queue):
    org_id, queue_id = test_org_queue

    job_a = await _create_job(queue_id, name="A")
    job_b = await _create_job(queue_id, name="B", status=JobStatus.blocked)
    job_c = await _create_job(queue_id, name="C", status=JobStatus.blocked)
    await _link(job_b.id, job_a.id)
    await _link(job_c.id, job_a.id)

    unblocked = await _complete_and_unblock(job_a.id, org_id)

    assert set(unblocked) == {job_b.id, job_c.id}
    assert await _status_of(job_b.id) == JobStatus.queued
    assert await _status_of(job_c.id) == JobStatus.queued


async def test_diamond_unblocks_final_job_only_after_both_branches_complete(test_org_queue):
    org_id, queue_id = test_org_queue

    job_a = await _create_job(queue_id, name="A")
    job_b = await _create_job(queue_id, name="B", status=JobStatus.blocked)
    job_c = await _create_job(queue_id, name="C", status=JobStatus.blocked)
    job_d = await _create_job(queue_id, name="D", status=JobStatus.blocked)
    await _link(job_b.id, job_a.id)
    await _link(job_c.id, job_a.id)
    await _link(job_d.id, job_b.id)
    await _link(job_d.id, job_c.id)

    await _complete_and_unblock(job_a.id, org_id)
    assert await _status_of(job_b.id) == JobStatus.queued
    assert await _status_of(job_c.id) == JobStatus.queued
    assert await _status_of(job_d.id) == JobStatus.blocked

    await _complete_and_unblock(job_b.id, org_id)
    assert await _status_of(job_d.id) == JobStatus.blocked

    await _complete_and_unblock(job_c.id, org_id)
    assert await _status_of(job_d.id) == JobStatus.queued


async def test_detect_cycle_returns_path(test_org_queue):
    _org_id, queue_id = test_org_queue

    job_a = await _create_job(queue_id, name="A")
    job_b = await _create_job(queue_id, name="B", status=JobStatus.blocked)
    job_c = await _create_job(queue_id, name="C", status=JobStatus.blocked)
    # A depends on B, B depends on C. Now try to make C depend on A -> cycle.
    await _link(job_a.id, job_b.id)
    await _link(job_b.id, job_c.id)

    async with AsyncSessionLocal() as db:
        has_cycle, path = await dependency_service.detect_cycle(job_c.id, [job_a.id], db)

    assert has_cycle is True
    assert path[0] == str(job_a.id)
    assert path[-1] == str(job_c.id)

    async with AsyncSessionLocal() as db:
        no_cycle, empty_path = await dependency_service.detect_cycle(
            job_c.id, [uuid.uuid4()], db
        )
    assert no_cycle is False
    assert empty_path == []


async def test_create_workflow_creates_diamond_in_one_call(test_org_queue):
    org_id, queue_id = test_org_queue

    payload = WorkflowCreateRequest(
        name="charge-and-notify",
        jobs=[
            WorkflowJobSpec(ref="charge-card", name="charge-card", queue_id=queue_id),
            WorkflowJobSpec(
                ref="send-receipt", name="send-receipt", queue_id=queue_id, depends_on=["charge-card"]
            ),
            WorkflowJobSpec(
                ref="update-ledger",
                name="update-ledger",
                queue_id=queue_id,
                depends_on=["charge-card"],
            ),
            WorkflowJobSpec(
                ref="close-order",
                name="close-order",
                queue_id=queue_id,
                depends_on=["send-receipt", "update-ledger"],
            ),
        ],
    )

    async with AsyncSessionLocal() as db:
        result = await job_service.create_workflow(db, org_id, payload)

    by_ref = {j.ref: j for j in result.jobs}
    assert set(by_ref) == {"charge-card", "send-receipt", "update-ledger", "close-order"}
    assert by_ref["charge-card"].status == JobStatus.queued
    assert by_ref["send-receipt"].status == JobStatus.blocked
    assert by_ref["update-ledger"].status == JobStatus.blocked
    assert by_ref["close-order"].status == JobStatus.blocked
    assert result.dependency_map["close-order"] == ["send-receipt", "update-ledger"]

    async with AsyncSessionLocal() as db:
        edges = (
            (
                await db.execute(
                    select(JobDependency.job_id, JobDependency.depends_on_job_id).where(
                        JobDependency.job_id == by_ref["close-order"].id
                    )
                )
            )
            .all()
        )
    assert {row[1] for row in edges} == {by_ref["send-receipt"].id, by_ref["update-ledger"].id}

    # Full end-to-end: complete charge-card, both mid jobs unblock; only after
    # BOTH complete does close-order unblock.
    await _complete_and_unblock(by_ref["charge-card"].id, org_id)
    assert await _status_of(by_ref["send-receipt"].id) == JobStatus.queued
    assert await _status_of(by_ref["update-ledger"].id) == JobStatus.queued
    assert await _status_of(by_ref["close-order"].id) == JobStatus.blocked

    await _complete_and_unblock(by_ref["send-receipt"].id, org_id)
    assert await _status_of(by_ref["close-order"].id) == JobStatus.blocked

    await _complete_and_unblock(by_ref["update-ledger"].id, org_id)
    assert await _status_of(by_ref["close-order"].id) == JobStatus.queued
