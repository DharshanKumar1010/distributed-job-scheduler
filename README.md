# Distributed Job Scheduler

A production-inspired distributed background job scheduling platform built with **FastAPI**, **PostgreSQL**, **Redis**, and **React**. The system supports asynchronous job execution, distributed workers, scheduling, retries, workflow dependencies, RBAC, real-time monitoring, and AI-powered failure analysis.

> Built as an internship assignment for Codity.AI to demonstrate backend engineering, distributed systems, database design, concurrency, and full-stack development.

---

## Features

### Job Scheduling
- Immediate jobs
- Delayed jobs
- Scheduled jobs
- Recurring (Cron) jobs
- Batch jobs

### Queue Management
- Multiple queues per project
- Queue priorities
- Pause / Resume queues
- Configurable concurrency limits
- Queue statistics
- Retry policies

### Worker System
- Distributed workers
- Atomic job claiming using PostgreSQL `FOR UPDATE SKIP LOCKED`
- Heartbeat monitoring
- Automatic crash recovery
- Graceful shutdown
- Queue sharding
- Worker concurrency

### Reliability
- Fixed retry strategy
- Linear retry strategy
- Exponential retry strategy
- Dead Letter Queue
- Execution history
- Job logs
- Retry metrics

### Workflow Engine
- Job dependencies
- DAG workflow execution
- Dependency tracking
- Automatic unblocking

### Security
- JWT Authentication
- Role Based Access Control (RBAC)
- Organizations
- Projects
- Permission-based APIs

### Dashboard
- Live worker monitoring
- Queue dashboard
- Job explorer
- Dead Letter Queue
- Workflow visualization
- Real-time WebSocket updates

### AI Integration
- AI-generated failure summaries
- Root cause analysis using Groq API

---

# Architecture

```
                    React Dashboard
                          │
                WebSocket / REST API
                          │
                   FastAPI Backend
                          │
        ┌─────────────────┴────────────────┐
        │                                  │
   PostgreSQL                         Redis
        │                                  │
        │                           Pub/Sub
        │                                  │
        ├──────────────┐                   │
        │              │                   │
     Worker 1       Worker N         Dispatcher
                        │
                    Reaper Service
```

---

# Tech Stack

## Backend

- FastAPI
- SQLAlchemy 2.0
- AsyncPG
- Alembic
- PostgreSQL
- Redis
- Pydantic
- JWT Authentication
- WebSockets

## Frontend

- React
- TypeScript
- Vite
- React Query
- Tailwind CSS
- Recharts

## AI

- Groq API

## Infrastructure

- Render
- Vercel
- Supabase
- Upstash Redis

---

# Project Structure

```
distributed-job-scheduler
│
├── backend
│   ├── app
│   ├── alembic
│   ├── tests
│   ├── requirements.txt
│   └── run_worker.py
│
├── frontend
│
├── docs
│   ├── architecture.md
│   ├── api-reference.md
│   ├── er-diagram.md
│   ├── design-decisions.md
│   └── test-coverage.md
│
└── docker-compose.yml
```

---

# Database

The system contains **13 normalized database tables**

- Organizations
- Users
- Projects
- Queues
- Retry Policies
- Workers
- Worker Heartbeats
- Jobs
- Job Executions
- Job Logs
- Scheduled Jobs
- Dead Letter Queue
- Job Dependencies

Highlights

- UUID Primary Keys
- Foreign Keys
- Cascading Deletes
- Indexed Claim Query
- Normalized Retry Policies

---

# Job Lifecycle

```
Queued
    │
    ▼
Claimed
    │
    ▼
Running
    │
 ┌──┴──────────────┐
 ▼                 ▼
Completed      Failed
                    │
            Retry Strategy
                    │
          ┌─────────┴─────────┐
          ▼                   ▼
      Requeued          Dead Letter Queue
```

---

# Concurrency

The scheduler prevents duplicate execution using PostgreSQL row locking.

```sql
FOR UPDATE SKIP LOCKED
```

Features include

- Atomic claiming
- Worker heartbeats
- Crash recovery
- Distributed locking
- Queue sharding

---

# API

The project exposes **49 REST endpoints**

- Authentication
- Organizations
- Projects
- Queues
- Jobs
- Workers
- Retry Policies
- Dead Letter Queue
- Workflow APIs
- WebSocket Endpoint

Interactive documentation

```
/docs
```

---

# Testing

The project contains **33 automated tests**

Tests include

- Retry strategies
- RBAC
- Worker concurrency
- Queue sharding
- Rate limiting
- Workflow dependencies

Run

```bash
pytest tests/
```

---

# Installation

## Clone

```bash
git clone https://github.com/DharshanKumar1010/distributed-job-scheduler.git
```

---

## Backend

```bash
cd backend

python -m venv venv

source venv/bin/activate
# Windows
venv\Scripts\activate

pip install -r requirements.txt

alembic upgrade head

uvicorn app.main:app --reload
```

---

## Worker

```bash
python -m app.worker.entrypoint
```

---

## Dispatcher

```bash
python -m app.scheduler.entrypoint
```

---

## Frontend

```bash
cd frontend

npm install

npm run dev
```

---

# Environment Variables

Create

```
backend/.env
```

```env
DATABASE_URL=
REDIS_URL=
SECRET_KEY=
ACCESS_TOKEN_EXPIRE_MINUTES=60

WORKER_CONCURRENCY=5
WORKER_POLL_INTERVAL_SECONDS=1
HEARTBEAT_INTERVAL_SECONDS=10
REAPER_INTERVAL_SECONDS=30

GROQ_API_KEY=
```

---

# Deployment

Backend
- Render

Frontend
- Vercel

Database
- Supabase PostgreSQL

Cache
- Upstash Redis

---

# Documentation

Additional documentation is available inside the `docs` folder.

- Architecture
- API Reference
- ER Diagram
- Design Decisions
- Test Coverage

---

# Highlights

- Production-inspired architecture
- Distributed workers
- Real-time monitoring
- WebSocket updates
- Queue sharding
- Distributed locking
- Workflow engine
- RBAC
- AI failure analysis
- PostgreSQL concurrency
- Redis Pub/Sub
- Async Python
- React Dashboard

---

# License

This project was developed for educational purposes as part of the Codity.AI internship assignment.
