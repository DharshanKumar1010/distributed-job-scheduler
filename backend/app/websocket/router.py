import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import func, select

from app.database import AsyncSessionLocal
from app.dependencies import verify_token
from app.exceptions import APIError
from app.models.job import Job, JobStatus
from app.models.project import Project
from app.models.queue import Queue
from app.models.user import User
from app.models.worker import Worker, WorkerStatus
from app.websocket.hub import hub

logger = logging.getLogger("websocket.router")

router = APIRouter(tags=["websocket"])

# 1008 = Policy Violation, the standard WS close code for "you're not allowed
# here". There's no WS equivalent of an HTTP 403, but sending this close
# frame *before* accept() causes uvicorn to reject the upgrade handshake
# itself (observed client-side as the connection failing), which is the
# closest real behavior to "403, not after accepting".
UNAUTHORIZED_CLOSE_CODE = 1008


async def _authenticate(token: str | None) -> User | None:
    if not token:
        return None
    try:
        payload = verify_token(token)
    except APIError:
        return None

    user_id = payload.get("sub")
    if user_id is None:
        return None

    async with AsyncSessionLocal() as db:
        user = await db.get(User, uuid.UUID(user_id))
        if user is None or not user.is_active:
            return None
        return user


async def _build_snapshot(org_id: uuid.UUID) -> dict:
    async with AsyncSessionLocal() as db:
        active_workers = await db.scalar(
            select(func.count())
            .select_from(Worker)
            .join(Queue, Queue.id == Worker.queue_id)
            .join(Project, Project.id == Queue.project_id)
            .where(Project.org_id == org_id, Worker.status != WorkerStatus.offline)
        )
        queued_jobs = await db.scalar(
            select(func.count())
            .select_from(Job)
            .join(Queue, Queue.id == Job.queue_id)
            .join(Project, Project.id == Queue.project_id)
            .where(Project.org_id == org_id, Job.status == JobStatus.queued)
        )
        running_jobs = await db.scalar(
            select(func.count())
            .select_from(Job)
            .join(Queue, Queue.id == Job.queue_id)
            .join(Project, Project.id == Queue.project_id)
            .where(Project.org_id == org_id, Job.status == JobStatus.running)
        )

    return {
        "active_workers": active_workers or 0,
        "queued_jobs": queued_jobs or 0,
        "running_jobs": running_jobs or 0,
    }


@router.websocket("/connect")
async def websocket_connect(websocket: WebSocket, token: str | None = None) -> None:
    user = await _authenticate(token)
    if user is None:
        await websocket.close(code=UNAUTHORIZED_CLOSE_CODE)
        return

    await websocket.accept()
    await hub.connect(websocket, user.id, user.org_id)

    try:
        snapshot = await _build_snapshot(user.org_id)
        await websocket.send_json(
            {
                "event": "snapshot",
                "data": snapshot,
                "ts": datetime.now(timezone.utc).isoformat(),
            }
        )

        while True:
            raw = await websocket.receive_text()
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if message.get("type") == "ping":
                await websocket.send_json(
                    {"type": "pong", "ts": datetime.now(timezone.utc).isoformat()}
                )
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for user %s (org %s)", user.id, user.org_id)
    finally:
        hub.disconnect(websocket)
