# Distributed Job Scheduler

A production-grade distributed job scheduling platform. Users submit jobs via
a REST API; workers atomically claim and execute them using PostgreSQL's
`FOR UPDATE SKIP LOCKED`; a React dashboard shows real-time queue health,
worker status, and execution logs over WebSockets.

See [Claud.md](./Claud.md) for the full technical spec, conventions, and
phase checklist that guide this project's development.

## Stack

| Layer | Technology |
|---|---|
| Backend API | FastAPI (async), Python 3.11+ |
| ORM | SQLAlchemy 2.0 (async) + Alembic |
| Database | PostgreSQL 15 |
| Cache / Pub-Sub | Redis 7 |
| Worker runtime | Python asyncio |
| Frontend | React 18 + TypeScript + Vite |
| Styling | Tailwind CSS + shadcn/ui |
| Charts | Recharts |
| Auth | JWT (python-jose) + bcrypt |

## Quick start

### 1. Start Postgres + Redis

```bash
docker compose up -d
```

### 2. Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

The API will be available at http://localhost:8000, with a health check at
http://localhost:8000/health.

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

The dashboard will be available at http://localhost:5173.

## Environment variables

Copy the defaults already present in `backend/.env` and `frontend/.env` for
local development. See `Claud.md` for the full list and descriptions.

## Project structure

```
/
├── Claud.md
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
│   │   └── websocket/
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
```
