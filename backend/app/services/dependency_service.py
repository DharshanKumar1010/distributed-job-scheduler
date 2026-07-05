import asyncio
import logging
import uuid
from datetime import datetime, timezone

from redis.asyncio import Redis
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.job import Job, JobStatus
from app.models.job_dependency import JobDependency
from app.websocket.publisher import publish_event

logger = logging.getLogger("dependency_service")

MAX_GRAPH_DEPTH = 20
MAX_UNBLOCK_DEPTH = 50

# Ancestors: everything `root_id` (transitively) depends on. Mirror image of
# DESCENDANTS_CTE below — walks from a node already in the tree to jobs it
# points at via job_dependencies.depends_on_job_id.
_ANCESTORS_CTE = text(
    """
    WITH RECURSIVE dep_tree AS (
        SELECT j.id, j.name, j.status, 0 as depth
        FROM jobs j
        WHERE j.id = :root_id
        UNION ALL
        SELECT j.id, j.name, j.status, dt.depth + 1
        FROM jobs j
        JOIN job_dependencies jd ON j.id = jd.depends_on_job_id
        JOIN dep_tree dt ON dt.id = jd.job_id
        WHERE dt.depth < :max_depth
    )
    SELECT id, name, status, depth FROM dep_tree ORDER BY depth
    """
)

# Descendants: everything that (transitively) depends on `root_id`.
_DESCENDANTS_CTE = text(
    """
    WITH RECURSIVE dep_tree AS (
        SELECT j.id, j.name, j.status, j.parent_job_id, 0 as depth
        FROM jobs j
        WHERE j.id = :root_id
        UNION ALL
        SELECT j.id, j.name, j.status, j.parent_job_id, dt.depth + 1
        FROM jobs j
        JOIN job_dependencies jd ON j.id = jd.job_id
        JOIN dep_tree dt ON dt.id = jd.depends_on_job_id
        WHERE dt.depth < :max_depth
    )
    SELECT id, name, status, depth FROM dep_tree ORDER BY depth
    """
)


async def get_direct_dependencies(job_id: uuid.UUID, db: AsyncSession) -> list[Job]:
    """Jobs that `job_id` directly depends on (one hop)."""
    result = await db.execute(
        select(Job).join(JobDependency, JobDependency.depends_on_job_id == Job.id).where(
            JobDependency.job_id == job_id
        )
    )
    return list(result.scalars().all())


async def get_direct_dependents(job_id: uuid.UUID, db: AsyncSession) -> list[Job]:
    """Jobs that directly depend on `job_id` (one hop)."""
    result = await db.execute(
        select(Job).join(JobDependency, JobDependency.job_id == Job.id).where(
            JobDependency.depends_on_job_id == job_id
        )
    )
    return list(result.scalars().all())


async def get_direct_dependents_with_status(job_id: uuid.UUID, db: AsyncSession) -> list[dict]:
    """Direct (one-hop) dependents of `job_id`, each annotated with whether
    it's ALSO waiting on some other, unrelated dependency.
    """
    dependents = await get_direct_dependents(job_id, db)

    output: list[dict] = []
    for dep_job in dependents:
        other_unmet = await db.scalar(
            select(func.count())
            .select_from(JobDependency)
            .join(Job, Job.id == JobDependency.depends_on_job_id)
            .where(
                JobDependency.job_id == dep_job.id,
                JobDependency.depends_on_job_id != job_id,
                Job.status != JobStatus.completed,
            )
        )
        output.append(
            {
                "job_id": dep_job.id,
                "name": dep_job.name,
                "status": dep_job.status,
                "queue_id": dep_job.queue_id,
                "blocked_on_others": (other_unmet or 0) > 0,
            }
        )
    return output


async def _edges_among(db: AsyncSession, node_ids: set[uuid.UUID]) -> list[tuple[uuid.UUID, uuid.UUID]]:
    if not node_ids:
        return []
    result = await db.execute(
        select(JobDependency.job_id, JobDependency.depends_on_job_id).where(
            JobDependency.job_id.in_(node_ids), JobDependency.depends_on_job_id.in_(node_ids)
        )
    )
    return list(result.all())


def _build_nested(
    node_id: uuid.UUID,
    nodes_by_id: dict[uuid.UUID, dict],
    children_by_parent: dict[uuid.UUID, list[uuid.UUID]],
    key: str,
    visited: set[uuid.UUID],
) -> dict:
    node = nodes_by_id[node_id]
    if node_id in visited:
        return {"job_id": node["id"], "name": node["name"], "status": node["status"], key: []}
    visited = visited | {node_id}

    children = [
        _build_nested(child_id, nodes_by_id, children_by_parent, key, visited)
        for child_id in children_by_parent.get(node_id, [])
        if child_id in nodes_by_id
    ]
    return {"job_id": node["id"], "name": node["name"], "status": node["status"], key: children}


async def get_dependency_graph(job_id: uuid.UUID, db: AsyncSession) -> dict:
    """Full DAG rooted at `job_id`: everything it (transitively) depends on,
    plus everything that (transitively) depends on it. Two recursive CTEs
    (one per direction) instead of N+1 per-node queries.
    """
    ancestor_rows = (
        await db.execute(_ANCESTORS_CTE, {"root_id": job_id, "max_depth": MAX_GRAPH_DEPTH})
    ).mappings().all()
    descendant_rows = (
        await db.execute(_DESCENDANTS_CTE, {"root_id": job_id, "max_depth": MAX_GRAPH_DEPTH})
    ).mappings().all()

    root_row = ancestor_rows[0] if ancestor_rows else descendant_rows[0]

    ancestor_ids = {row["id"] for row in ancestor_rows}
    descendant_ids = {row["id"] for row in descendant_rows}

    nodes_by_id: dict[uuid.UUID, dict] = {}
    for row in list(ancestor_rows) + list(descendant_rows):
        nodes_by_id[row["id"]] = dict(row)

    # depends_on edges: child -> [things it depends on], restricted to the
    # ancestor set so the nested tree only grows "upward".
    dep_edges = await _edges_among(db, ancestor_ids)
    depends_on_children: dict[uuid.UUID, list[uuid.UUID]] = {}
    for child_id, parent_id in dep_edges:
        depends_on_children.setdefault(child_id, []).append(parent_id)

    # dependents edges: parent -> [things that depend on it], restricted to
    # the descendant set.
    dependent_edges = await _edges_among(db, descendant_ids)
    dependents_children: dict[uuid.UUID, list[uuid.UUID]] = {}
    for child_id, parent_id in dependent_edges:
        dependents_children.setdefault(parent_id, []).append(child_id)

    depends_on_tree = _build_nested(job_id, nodes_by_id, depends_on_children, "depends_on", set())
    dependents_tree = _build_nested(job_id, nodes_by_id, dependents_children, "dependents", set())

    return {
        "job_id": root_row["id"],
        "name": root_row["name"],
        "status": root_row["status"],
        "depends_on": depends_on_tree["depends_on"],
        "dependents": dependents_tree["dependents"],
    }


def collect_all_job_ids(node: dict) -> list[uuid.UUID]:
    """Walks a get_dependency_graph() result and flattens every job_id in it."""
    ids = {node["job_id"]}
    for child in node.get("depends_on", []):
        ids.update(collect_all_job_ids(child))
    for child in node.get("dependents", []):
        ids.update(collect_all_job_ids(child))
    return list(ids)


async def detect_cycle(
    job_id: uuid.UUID, depends_on_ids: list[uuid.UUID], db: AsyncSession
) -> tuple[bool, list[str]]:
    """Would adding edges job_id -> depends_on_ids create a cycle?

    Iterative DFS (not recursive) from each candidate dependency, walking
    further into ITS dependencies, looking for a path back to job_id.
    Avoids Python's recursion limit on deep/pathological graphs.
    """
    visited: set[uuid.UUID] = set()
    stack: list[tuple[uuid.UUID, list[str]]] = [(dep_id, [str(dep_id)]) for dep_id in depends_on_ids]

    while stack:
        current_id, path = stack.pop()
        if current_id == job_id:
            return True, path
        if current_id in visited:
            continue
        visited.add(current_id)

        children = await get_direct_dependencies(current_id, db)
        for child in children:
            stack.append((child.id, path + [str(child.id)]))

    return False, []


async def get_workflow_status(job_ids: list[uuid.UUID], db: AsyncSession) -> dict:
    """Aggregate status counts across a set of jobs via a single COUNT FILTER
    query (not N per-status queries).
    """
    if not job_ids:
        return {
            "total": 0,
            "completed": 0,
            "running": 0,
            "blocked": 0,
            "failed": 0,
            "dead": 0,
            "queued": 0,
            "progress_pct": 0.0,
        }

    row = (
        await db.execute(
            select(
                func.count().label("total"),
                func.count().filter(Job.status == JobStatus.completed).label("completed"),
                func.count().filter(Job.status == JobStatus.running).label("running"),
                func.count().filter(Job.status == JobStatus.blocked).label("blocked"),
                func.count().filter(Job.status == JobStatus.failed).label("failed"),
                func.count().filter(Job.status == JobStatus.dead).label("dead"),
                func.count().filter(Job.status == JobStatus.queued).label("queued"),
            )
            .select_from(Job)
            .where(Job.id.in_(job_ids))
        )
    ).one()

    total = row.total or 0
    completed = row.completed or 0
    progress_pct = round((completed / total * 100), 1) if total else 0.0

    return {
        "total": total,
        "completed": completed,
        "running": row.running or 0,
        "blocked": row.blocked or 0,
        "failed": row.failed or 0,
        "dead": row.dead or 0,
        "queued": row.queued or 0,
        "progress_pct": progress_pct,
    }


async def check_and_unblock(
    completed_job_id: uuid.UUID,
    db: AsyncSession,
    redis: Redis | None,
    org_id: uuid.UUID | None,
    _depth: int = 0,
) -> list[uuid.UUID]:
    """Call after a job reaches `completed`. Finds direct dependents that are
    `blocked`, and for each one whose deps are now ALL completed, flips it to
    `queued`, publishes `job.unblocked`, and recurses (so chains A->B->C fully
    unblock in one pass). Fan-in siblings unblocked by the same completion are
    resolved concurrently via asyncio.gather.
    """
    if _depth >= MAX_UNBLOCK_DEPTH:
        logger.warning("check_and_unblock exceeded max depth %d at %s", MAX_UNBLOCK_DEPTH, completed_job_id)
        return []

    completed_job = await db.get(Job, completed_job_id)

    candidates_result = await db.execute(
        select(Job)
        .join(JobDependency, JobDependency.job_id == Job.id)
        .where(JobDependency.depends_on_job_id == completed_job_id, Job.status == JobStatus.blocked)
    )
    candidates = list(candidates_result.scalars().all())

    newly_unblocked: list[Job] = []
    for candidate in candidates:
        remaining = await db.scalar(
            select(func.count())
            .select_from(JobDependency)
            .join(Job, Job.id == JobDependency.depends_on_job_id)
            .where(JobDependency.job_id == candidate.id, Job.status != JobStatus.completed)
        )
        if (remaining or 0) != 0:
            continue

        await db.execute(
            update(Job)
            .where(Job.id == candidate.id)
            .values(status=JobStatus.queued, updated_at=datetime.now(timezone.utc))
        )
        newly_unblocked.append(candidate)

    if newly_unblocked:
        await db.commit()

    if redis is not None and org_id is not None:
        for candidate in newly_unblocked:
            try:
                await publish_event(
                    redis,
                    org_id,
                    "job.unblocked",
                    {
                        "job_id": str(candidate.id),
                        "name": candidate.name,
                        "queue_id": str(candidate.queue_id),
                        "unblocked_by": str(completed_job_id),
                        "unblocked_by_name": completed_job.name if completed_job else None,
                    },
                )
            except Exception:
                logger.exception("Failed to publish job.unblocked for %s", candidate.id)

    unblocked_ids = [candidate.id for candidate in newly_unblocked]

    if unblocked_ids:
        # Each recursive branch gets its own session: a single AsyncSession
        # cannot be driven concurrently, and gather() below runs these
        # branches (e.g. a diamond's two arms) in parallel.
        await asyncio.gather(
            *[_check_and_unblock_isolated(jid, redis, org_id, _depth + 1) for jid in unblocked_ids]
        )

    return unblocked_ids


async def _check_and_unblock_isolated(
    job_id: uuid.UUID, redis: Redis | None, org_id: uuid.UUID | None, depth: int
) -> list[uuid.UUID]:
    async with AsyncSessionLocal() as db:
        return await check_and_unblock(job_id, db, redis, org_id, depth)
