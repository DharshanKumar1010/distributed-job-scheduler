# Distributed Job Scheduler

A production-grade distributed job scheduling platform. Users submit jobs via
a REST API; workers atomically claim and execute them using PostgreSQL's
`FOR UPDATE SKIP LOCKED`; a React dashboard shows real-time queue health,
worker status, live DAG workflows, and AI-powered failure analysis over
WebSockets.

Built across 13 phases — the core assignment (auth, queues, all 5 job types,
atomic claiming, retries/DLQ, a live dashboard) plus five bonus phases that
go well beyond it: a full DAG workflow engine, Redis-backed rate limiting
and distributed locking, consistent-hashing queue sharding, role-based
access control, and Groq-powered root-cause analysis on failed jobs.

**33/33 automated tests passing · 49 REST endpoints · 13 database tables ·
zero TypeScript errors.**

See [`CLAUDE.md`](./CLAUDE.md) for the full technical spec, conventions, and
phase checklist that guided development, and [`docs/`](./docs) for
architecture, ER diagram, API reference, design decisions, and test
coverage writeups.

## Stack

| Layer | Technology |
|---|---|
| Backend API | FastAPI (async), Python 3.11+ |
| ORM | SQLAlchemy 2.0 (async) + Alembic |
| Database | PostgreSQL 15 |
| Cache / Pub-Sub / Locks | Redis 7 |
| Worker runtime | Python asyncio (no Celery/RQ/ARQ) |
| Cron parsing | croniter |
| Frontend | React 18 + TypeScript + Vite |
| Styling | Tailwind CSS |
| Charts | Recharts + hand-rolled SVG (DAG canvas, shard map) |
| Auth | JWT (python-jose) + bcrypt, 29-permission RBAC |
| AI | Groq API (DLQ root-cause analysis, graceful fallback) |
| Testing | pytest + pytest-asyncio + httpx, against real Postgres/Redis |

## Quick start

### 1. Start Postgres + Redis

```bash
docker compose up -d
```

### 2. Backend API

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

API at http://localhost:8000, interactive docs at http://localhost:8000/docs,
health check at http://localhost:8000/health.

### 3. Worker (run at least one per queue)

```bash
cd backend
QUEUE_ID=<your-queue-uuid> python -m app.worker.entrypoint
```

Set `SHARD_ID=<n>` instead of leaving it unset if you want a worker pinned
to a fixed shard rather than dynamically self-assigned (see
[`docs/design-decisions.md`](./docs/design-decisions.md#5-consistent-hashing-over-a-redis-backed-worker-registry--not-a-fixed-hash-ring)).

### 4. Dispatcher + reaper (materializes scheduled/cron jobs, recovers dead workers)

```bash
cd backend
python -m app.scheduler.entrypoint
```

Safe to run more than one — they elect a single leader via a Postgres
advisory lock and fail over automatically.

### 5. Frontend

```bash
cd frontend
npm install
npm run dev
```

Dashboard at http://localhost:5173.

## Environment variables

Copy the defaults already present in `backend/.env` and `frontend/.env` for
local development. `GROQ_API_KEY` is optional — the AI failure-analysis
feature degrades to a fully-structured static analysis (using the same
error-classification heuristics) if it isn't set. See `CLAUDE.md` for the
full list.

## Running the tests

```bash
cd backend
pytest tests/ -v --tb=short
```

All 33 tests run against a real Postgres + Redis instance (started via
`docker compose up -d`) — nothing is mocked. See
[`docs/test-coverage.md`](./docs/test-coverage.md) for what each test file
proves.

## Documentation

| Doc | Contents |
|---|---|
| [`docs/architecture.md`](./docs/architecture.md) | System diagram, process inventory, why this shape |
| [`docs/er-diagram.md`](./docs/er-diagram.md) | Full ERD for all 13 tables + indexing rationale |
| [`docs/api-reference.md`](./docs/api-reference.md) | All 49 endpoints, grouped, with request/response examples |
| [`docs/design-decisions.md`](./docs/design-decisions.md) | Six trade-off writeups: queue-on-Postgres, visibility timeout, DAG via recursive CTE, dual rate limiters, consistent-hashing shards, fire-and-forget AI |
| [`docs/test-coverage.md`](./docs/test-coverage.md) | All 33 tests, grouped by file, with the most important test walked through |
| [`docs/submission.pdf`](./docs/submission.pdf) | Print-ready summary of all of the above |

## Project structure

```
/
├── CLAUDE.md
├── README.md
├── docker-compose.yml
├── docs/
│   ├── architecture.md
│   ├── er-diagram.md
│   ├── api-reference.md
│   ├── design-decisions.md
│   ├── test-coverage.md
│   └── submission.pdf
├── backend/
│   ├── app/
│   │   ├── main.py, config.py, database.py, dependencies.py, exceptions.py
│   │   ├── auth/          # permission constants + role matrix
│   │   ├── models/        # 13 SQLAlchemy tables
│   │   ├── schemas/       # Pydantic v2 request/response models
│   │   ├── routers/       # 11 route families, 49 endpoints
│   │   ├── services/      # business logic, one module per domain
│   │   ├── middleware/    # sliding-window rate limiter
│   │   ├── worker/        # claim loop, retries, sharding, rate limiting
│   │   ├── scheduler/     # dispatcher, reaper, distributed locks
│   │   └── websocket/     # connection hub, Redis subscriber, publisher
│   ├── alembic/versions/  # migrations
│   ├── tests/             # 33 tests, 6 files
│   └── requirements.txt
└── frontend/
    ├── src/
    │   ├── pages/          # 9 pages incl. Workflows, Settings
    │   ├── components/     # DagCanvas, ShardDistribution, AiSummaryCard, Toast, ...
    │   ├── hooks/          # React Query hooks, usePermissions, useWebSocket
    │   ├── api/            # typed API client functions
    │   ├── store/          # Zustand: auth, live stats, toasts
    │   └── types/          # shared TS types mirroring backend schemas
    └── package.json
```
