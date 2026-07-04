import uuid

import pytest_asyncio
from sqlalchemy import delete

from app.database import AsyncSessionLocal
from app.models.dead_letter_queue import DeadLetterQueueEntry
from app.models.job import Job
from app.models.organization import Organization
from app.models.project import Project
from app.models.queue import Queue
from app.models.worker import Worker


@pytest_asyncio.fixture
async def test_queue():
    """Creates a throwaway org/project/queue for a test, and cleans it up after."""
    async with AsyncSessionLocal() as db:
        suffix = uuid.uuid4().hex[:8]
        org = Organization(name="Test Org", slug=f"test-org-{suffix}")
        db.add(org)
        await db.flush()

        project = Project(org_id=org.id, name="Test Project", slug=f"test-project-{suffix}")
        db.add(project)
        await db.flush()

        queue = Queue(project_id=project.id, name="Test Queue", slug=f"test-queue-{suffix}")
        db.add(queue)
        await db.commit()
        await db.refresh(queue)

        queue_id = queue.id
        org_id = org.id

    yield queue_id

    async with AsyncSessionLocal() as db:
        # Job/Worker FKs to queues.id aren't ON DELETE CASCADE, so clean them up
        # explicitly before letting the org->project->queue cascade finish the rest.
        await db.execute(delete(DeadLetterQueueEntry).where(DeadLetterQueueEntry.queue_id == queue_id))
        await db.execute(delete(Job).where(Job.queue_id == queue_id))
        await db.execute(delete(Worker).where(Worker.queue_id == queue_id))
        await db.execute(delete(Organization).where(Organization.id == org_id))
        await db.commit()
