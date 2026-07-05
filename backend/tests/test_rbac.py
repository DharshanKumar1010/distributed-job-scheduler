import uuid

from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy import delete

from app.config import settings
from app.database import AsyncSessionLocal
from app.main import app
from app.models.organization import Organization
from app.models.project import Project
from app.models.queue import Queue
from app.models.user import User, UserRole
from app.services.auth_service import hash_password

PASSWORD = "password123"

# ASGITransport doesn't run the app's lifespan (which normally sets this up
# and starts a Redis subscriber we don't need here), so the get_redis
# dependency's `request.app.state.redis_client` has to be provided directly.
_test_redis_client: Redis | None = None


def _client() -> AsyncClient:
    global _test_redis_client
    if _test_redis_client is None:
        _test_redis_client = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    app.state.redis_client = _test_redis_client
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _create_org_with_user(role: UserRole) -> tuple[uuid.UUID, uuid.UUID, str]:
    """Creates a throwaway org with one user of the given role. Returns
    (org_id, user_id, email).
    """
    suffix = uuid.uuid4().hex[:10]
    async with AsyncSessionLocal() as db:
        org = Organization(name="RBAC Test Org", slug=f"rbac-org-{suffix}")
        db.add(org)
        await db.flush()

        email = f"{role.value}-{suffix}@example.com"
        user = User(
            org_id=org.id,
            email=email,
            hashed_password=hash_password(PASSWORD),
            full_name=role.value,
            role=role,
        )
        db.add(user)
        await db.commit()
        await db.refresh(org)
        await db.refresh(user)
        return org.id, user.id, email


async def _add_user_to_org(org_id: uuid.UUID, role: UserRole) -> tuple[uuid.UUID, str]:
    suffix = uuid.uuid4().hex[:10]
    email = f"{role.value}-{suffix}@example.com"
    async with AsyncSessionLocal() as db:
        user = User(
            org_id=org_id,
            email=email,
            hashed_password=hash_password(PASSWORD),
            full_name=role.value,
            role=role,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user.id, email


async def _create_project_and_queue(org_id: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    suffix = uuid.uuid4().hex[:10]
    async with AsyncSessionLocal() as db:
        project = Project(org_id=org_id, name="RBAC Project", slug=f"rbac-project-{suffix}")
        db.add(project)
        await db.flush()
        queue = Queue(project_id=project.id, name="RBAC Queue", slug=f"rbac-queue-{suffix}")
        db.add(queue)
        await db.commit()
        await db.refresh(project)
        await db.refresh(queue)
        return project.id, queue.id


async def _cleanup_org(org_id: uuid.UUID, queue_ids: list[uuid.UUID] | None = None) -> None:
    async with AsyncSessionLocal() as db:
        # Queue->Project has no cascading delete, so drop queues first;
        # deleting the org then cascades to its projects and users.
        for queue_id in queue_ids or []:
            await db.execute(delete(Queue).where(Queue.id == queue_id))
        await db.execute(delete(Organization).where(Organization.id == org_id))
        await db.commit()


async def _login(client: AsyncClient, email: str) -> str:
    resp = await client.post("/auth/login", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def test_viewer_cannot_create_jobs():
    org_id, _user_id, email = await _create_org_with_user(UserRole.viewer)
    _project_id, queue_id = await _create_project_and_queue(org_id)
    try:
        async with _client() as client:
            token = await _login(client, email)
            resp = await client.post(
                f"/queues/{queue_id}/jobs",
                json={"name": "job-1", "payload": {}, "job_type": "immediate"},
                headers=_auth(token),
            )
        assert resp.status_code == 403
        body = resp.json()
        assert body["error"]["code"] == "INSUFFICIENT_PERMISSIONS"
        assert body["error"]["details"]["required_permission"] == "job:create"
        assert "owner" in body["error"]["details"]["roles_with_this_permission"]
    finally:
        await _cleanup_org(org_id, [queue_id])


async def test_viewer_can_read_jobs():
    org_id, _user_id, email = await _create_org_with_user(UserRole.viewer)
    _project_id, queue_id = await _create_project_and_queue(org_id)
    try:
        async with _client() as client:
            token = await _login(client, email)
            resp = await client.get(f"/queues/{queue_id}/jobs", headers=_auth(token))
        assert resp.status_code == 200
    finally:
        await _cleanup_org(org_id, [queue_id])


async def test_member_can_create_but_not_delete_queues():
    org_id, _user_id, email = await _create_org_with_user(UserRole.member)
    project_id, queue_id = await _create_project_and_queue(org_id)
    new_queue_id = None
    try:
        async with _client() as client:
            token = await _login(client, email)

            create_resp = await client.post(
                f"/projects/{project_id}/queues",
                json={"name": "member-queue", "slug": f"member-queue-{uuid.uuid4().hex[:8]}"},
                headers=_auth(token),
            )
            assert create_resp.status_code == 201
            new_queue_id = uuid.UUID(create_resp.json()["data"]["id"])

            delete_resp = await client.delete(
                f"/projects/{project_id}/queues/{queue_id}", headers=_auth(token)
            )
        assert delete_resp.status_code == 403
        assert delete_resp.json()["error"]["code"] == "INSUFFICIENT_PERMISSIONS"
    finally:
        await _cleanup_org(org_id, [queue_id, new_queue_id] if new_queue_id else [queue_id])


async def test_admin_can_do_everything_except_promote_to_owner():
    org_id, _admin_id, admin_email = await _create_org_with_user(UserRole.admin)
    other_user_id, _other_email = await _add_user_to_org(org_id, UserRole.member)
    project_id, queue_id = await _create_project_and_queue(org_id)
    new_queue_id: uuid.UUID | None = None
    try:
        async with _client() as client:
            token = await _login(client, admin_email)

            # Admin CAN do ordinary privileged actions (e.g. create a queue).
            create_resp = await client.post(
                f"/projects/{project_id}/queues",
                json={"name": "admin-queue", "slug": f"admin-queue-{uuid.uuid4().hex[:8]}"},
                headers=_auth(token),
            )
            assert create_resp.status_code == 201
            new_queue_id = uuid.UUID(create_resp.json()["data"]["id"])

            # But cannot promote anyone to owner.
            promote_resp = await client.patch(
                f"/orgs/{org_id}/users/{other_user_id}",
                json={"role": "owner"},
                headers=_auth(token),
            )
        assert promote_resp.status_code == 403
        assert promote_resp.json()["error"]["code"] == "INSUFFICIENT_PERMISSIONS"
    finally:
        await _cleanup_org(org_id, [queue_id, new_queue_id] if new_queue_id else [queue_id])


async def test_owner_can_promote_to_admin():
    org_id, _owner_id, owner_email = await _create_org_with_user(UserRole.owner)
    other_user_id, _other_email = await _add_user_to_org(org_id, UserRole.member)
    try:
        async with _client() as client:
            token = await _login(client, owner_email)
            resp = await client.patch(
                f"/orgs/{org_id}/users/{other_user_id}",
                json={"role": "admin"},
                headers=_auth(token),
            )
        assert resp.status_code == 200
        assert resp.json()["data"]["role"] == "admin"
    finally:
        await _cleanup_org(org_id)


async def test_cross_org_access_is_blocked_regardless_of_role():
    org_a_id, _user_a_id, email_a = await _create_org_with_user(UserRole.owner)
    org_b_id, _user_b_id, _email_b = await _create_org_with_user(UserRole.owner)
    _project_b_id, queue_b_id = await _create_project_and_queue(org_b_id)
    try:
        async with _client() as client:
            token_a = await _login(client, email_a)
            # org A's owner (full permissions) still can't reach org B's queue.
            resp = await client.get(f"/queues/{queue_b_id}/jobs", headers=_auth(token_a))
        assert resp.status_code == 404
    finally:
        await _cleanup_org(org_a_id)
        await _cleanup_org(org_b_id, [queue_b_id])
