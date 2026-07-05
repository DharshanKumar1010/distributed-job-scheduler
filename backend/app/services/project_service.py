import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import APIError
from app.models.project import Project


async def list_projects(
    db: AsyncSession, org_id: uuid.UUID, page: int, limit: int
) -> tuple[list[Project], int]:
    total = await db.scalar(
        select(func.count())
        .select_from(Project)
        .where(Project.org_id == org_id, Project.is_active.is_(True))
    )
    result = await db.execute(
        select(Project)
        .where(Project.org_id == org_id, Project.is_active.is_(True))
        .order_by(Project.created_at.asc())
        .offset((page - 1) * limit)
        .limit(limit)
    )
    return list(result.scalars().all()), total or 0


async def _check_slug_available(
    db: AsyncSession,
    org_id: uuid.UUID,
    slug: str,
    exclude_project_id: uuid.UUID | None = None,
) -> None:
    stmt = select(Project).where(Project.org_id == org_id, Project.slug == slug)
    if exclude_project_id is not None:
        stmt = stmt.where(Project.id != exclude_project_id)
    existing = await db.scalar(stmt)
    if existing is not None:
        raise APIError(
            409,
            "PROJECT_SLUG_TAKEN",
            "A project with this slug already exists in this organization",
        )


async def create_project(
    db: AsyncSession, org_id: uuid.UUID, name: str, slug: str, description: str | None
) -> Project:
    await _check_slug_available(db, org_id, slug)
    project = Project(org_id=org_id, name=name, slug=slug, description=description)
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


async def get_project(
    db: AsyncSession, org_id: uuid.UUID, project_id: uuid.UUID
) -> Project:
    project = await db.scalar(
        select(Project).where(
            Project.id == project_id,
            Project.org_id == org_id,
            Project.is_active.is_(True),
        )
    )
    if project is None:
        raise APIError(404, "PROJECT_NOT_FOUND", "Project not found")
    return project


async def update_project(
    db: AsyncSession, org_id: uuid.UUID, project_id: uuid.UUID, data: dict
) -> Project:
    project = await get_project(db, org_id, project_id)
    if "slug" in data and data["slug"] != project.slug:
        await _check_slug_available(
            db, org_id, data["slug"], exclude_project_id=project.id
        )
    for field, value in data.items():
        setattr(project, field, value)
    await db.commit()
    await db.refresh(project)
    return project


async def soft_delete_project(
    db: AsyncSession, org_id: uuid.UUID, project_id: uuid.UUID
) -> Project:
    project = await get_project(db, org_id, project_id)
    project.is_active = False
    await db.commit()
    await db.refresh(project)
    return project
