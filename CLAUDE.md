# CLAUDE.md — Distributed Job Scheduler

> Claude Code reads this file automatically at the start of every session.
> Never delete or rename it. Update it as the project evolves.

---

## What this project is

A production-grade distributed job scheduling platform. Users submit jobs
via REST API; workers atomically claim and execute them; a dashboard shows
real-time queue health, worker status, and execution logs.

---

## Stack (do not deviate without asking)

| Layer | Technology |
|---|---|
| Backend API | FastAPI (async), Python 3.11+ |
| ORM | SQLAlchemy 2.0 (async) |
| Migrations | Alembic |
| Database | PostgreSQL 15 (Supabase or local Docker) |
| Cache / Pub-Sub | Redis 7 |
| Worker runtime | Python asyncio (NOT Celery, NOT RQ, NOT ARQ) |
| Cron parsing | `croniter` |
| Frontend | React 18 + TypeScript + Vite |
| Styling | Tailwind CSS + shadcn/ui |
| Charts | Recharts |
| Live updates | FastAPI WebSockets + Redis pub/sub |
| Auth | JWT (python-jose) + bcrypt |
| Testing | pytest + pytest-asyncio + httpx |
| Deploy | Render (backend/worker) + Vercel (frontend) |

---

## Folder structure
/
├── CLAUDE.md
├── docker-compose.yml
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── routers/
│   │   ├── services/
│   │   ├── worker/
│   │   ├── scheduler/
│   │   ├── websocket/
│   │   └── dependencies.py
│   ├── alembic/
│   ├── tests/
│   └── requirements.txt
└── frontend/
├── src/
│   ├── components/
│   ├── pages/
│   ├── hooks/
│   ├── api/
│   ├── store/
│   └── types/
└── package.json

---

## Job status lifecycle — the only allowed transitions
QUEUED → CLAIMED → RUNNING → COMPLETED
→ FAILED → (retry?) → QUEUED
→ DEAD (max retries exceeded → DLQ)
QUEUED → CANCELLED
SCHEDULED → QUEUED          (dispatcher materializes it when due)
BLOCKED → QUEUED            (workflow deps: all parents COMPLETED)

Status values as a Python Enum:
`queued, scheduled, claimed, running, completed, failed, dead, cancelled, blocked`

---

## THE MOST IMPORTANT RULE — atomic job claiming

**NEVER use application-level locking. ALWAYS use this exact pattern:**

```sql
UPDATE jobs
SET
  status      = 'claimed',
  worker_id   = :worker_id,
  claimed_at  = now(),
  attempts    = attempts + 1
WHERE id = (
  SELECT id FROM jobs
  WHERE queue_id = :queue_id
    AND status   = 'queued'
    AND (scheduled_at IS NULL OR scheduled_at <= now())
  ORDER BY priority DESC, created_at ASC
  FOR UPDATE SKIP LOCKED
  LIMIT 1
)
RETURNING *;
```

`FOR UPDATE SKIP LOCKED` is what prevents two workers ever running the same job.
This is the single most important technical concept in the entire project.
If asked to implement job claiming in any other way, refuse and use this pattern.

---

## Retry backoff strategies

Given `attempt_number` (1-indexed) and `base_delay` in seconds:

```python
def compute_next_run(strategy: str, base_delay: int, attempt: int) -> datetime:
    if strategy == "fixed":
        delta = base_delay
    elif strategy == "linear":
        delta = base_delay * attempt
    elif strategy == "exponential":
        delta = base_delay * (2 ** (attempt - 1))
    return datetime.utcnow() + timedelta(seconds=delta)
```

---

## Heartbeat + reaper contract

- Workers MUST send a heartbeat UPDATE to `worker_heartbeats` every **10 seconds**.
- The reaper process checks every **30 seconds** for workers with `last_seen < now() - 45s`.
- Stale jobs (status=running, worker gone) are reset: `status='queued', worker_id=NULL`.
- A job re-queued by the reaper still counts toward `attempts`.

---

## WebSocket event format

All WebSocket messages are JSON with this envelope:

```json
{
  "event": "job.updated",
  "data": { ...event-specific payload... },
  "ts": "2025-01-01T00:00:00Z"
}
```

Event names: `job.created`, `job.updated`, `job.completed`, `job.failed`,
`job.dead`, `worker.connected`, `worker.disconnected`, `queue.stats`.

---

## API conventions

- All list endpoints: `GET /resource?page=1&limit=20&status=queued&queue_id=...`
- All responses: `{ "data": ..., "meta": { "total": N, "page": P, "limit": L } }`
- All errors: `{ "error": { "code": "QUEUE_NOT_FOUND", "message": "...", "details": {} } }`
- Auth: `Authorization: Bearer <jwt>` header on all protected routes
- Idempotency: job creation accepts optional `X-Idempotency-Key` header

---

## Environment variables (all required)
DATABASE_URL=postgresql+asyncpg://scheduler:scheduler@localhost:5432/scheduler
REDIS_URL=redis://localhost:6379
SECRET_KEY=change-me-in-production
ACCESS_TOKEN_EXPIRE_MINUTES=60
WORKER_CONCURRENCY=10
WORKER_POLL_INTERVAL_SECONDS=1
HEARTBEAT_INTERVAL_SECONDS=10
REAPER_INTERVAL_SECONDS=30
ANTHROPIC_API_KEY=sk-...

---

## What to do when stuck

1. Re-read the relevant section of this file first.
2. Check `backend/tests/` — the test for that feature may already document intent.
3. Do not change the DB schema without creating an Alembic migration.
4. Do not add new dependencies without updating `requirements.txt`.
5. Do not use `asyncio.sleep` in the web API layer — only in worker/scheduler processes.

---

## Completed phases (update this as you finish each one)

- [x] Phase 0 — Scaffold + Docker + CLAUDE.md
- [x] Phase 1 — Schema + Alembic migrations
- [x] Phase 2 — Auth + Orgs + Projects + Queues
- [x] Phase 3 — Job submission API (all 5 job types)
- [x] Phase 4 — Worker process (claim, execute, heartbeat, graceful shutdown)
- [x] Phase 5 — Retries + DLQ + Reaper
- [x] Phase 6 — Dashboard (React)
- [ ] Phase 7 — WebSocket live updates
- [ ] Phase 8 — Workflow dependencies (DAG)
- [ ] Phase 9 — Rate limiting + distributed locking
- [ ] Phase 10 — Queue sharding
- [ ] Phase 11 — RBAC
- [ ] Phase 12 — AI failure summaries