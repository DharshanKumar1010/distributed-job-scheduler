# API Reference

Base URL: `http://localhost:8000` (dev). Interactive Swagger UI is always
available at **`/docs`** — this document is the grouped, example-driven
companion to it, not a replacement.

- **Auth**: `Authorization: Bearer <jwt>` on every route except
  `POST /auth/register`, `POST /auth/login`.
- **Envelope**: list endpoints return `{ "data": [...], "meta": { "total", "page", "limit" } }`;
  single-resource endpoints return `{ "data": {...} }`; errors return
  `{ "error": { "code", "message", "details" } }`.
- **Idempotency**: `POST /queues/{id}/jobs` accepts an optional
  `X-Idempotency-Key` header — replaying the same key returns the original
  job instead of creating a duplicate.
- **Rate limits**: every route is sliding-window limited per user
  (`auth` 20/min, `job_write` 100/min, `job_read` 500/min, `queue_write`
  60/min, everything else 200/min). A 429 includes `X-RateLimit-*` and
  `Retry-After` headers.
- **Permissions**: routes are gated by one of 29 fine-grained permissions
  (see [`design-decisions.md`](./design-decisions.md)); the permission
  required is noted per route below.

49 endpoints total, grouped into 10 route families.

---

## 1. Auth (4 routes) — `app/routers/auth.py`

| Method | Path | Permission | Description |
|---|---|---|---|
| POST | `/auth/register` | public | Create an org + owner user, returns a JWT |
| POST | `/auth/login` | public | Exchange email/password for a JWT |
| GET | `/auth/me` | authenticated | Current user profile |
| GET | `/auth/permissions` | authenticated | Current user's full permission set + what they're missing |

**Example — register**
```http
POST /auth/register
{
  "org_name": "Acme Inc", "org_slug": "acme",
  "email": "owner@acme.com", "password": "supersecret123", "full_name": "Ada Owner"
}
```
```json
{ "data": { "access_token": "eyJ...", "token_type": "bearer",
  "user": { "id": "...", "org_id": "...", "email": "owner@acme.com", "role": "owner", "is_active": true } } }
```

**Example — permissions**
```json
{ "data": { "role": "member", "permissions": ["job:create", "job:read", "..."],
  "cannot_do": ["org:delete", "queue:delete", "..."] } }
```

---

## 2. Organizations & Users (6 routes) — `app/routers/organizations.py`

| Method | Path | Permission | Description |
|---|---|---|---|
| GET | `/orgs/{org_id}` | `org:read` | Org profile |
| PATCH | `/orgs/{org_id}` | `org:update` | Update org name/plan |
| GET | `/orgs/{org_id}/users` | `user:read` | List team members |
| POST | `/orgs/{org_id}/users` | `user:invite` | Invite a user (returns a one-time temp password) |
| PATCH | `/orgs/{org_id}/users/{user_id}` | `user:update_role` | Change a user's role (owner-only in practice — admins lack this permission) |
| DELETE | `/orgs/{org_id}/users/{user_id}` | `user:remove` | Deactivate a team member (self-removal blocked) |

**Example — invite**
```json
POST /orgs/{org_id}/users  { "email": "dev@acme.com", "role": "member" }
→ { "data": { "user": {...}, "temporary_password": "f-hUpnmsuXA06EN7" } }
```

---

## 3. Projects (5 routes) — `app/routers/projects.py`

| Method | Path | Permission |
|---|---|---|
| GET | `/orgs/{org_id}/projects` | `project:read` |
| POST | `/orgs/{org_id}/projects` | `project:create` |
| GET | `/orgs/{org_id}/projects/{project_id}` | `project:read` |
| PATCH | `/orgs/{org_id}/projects/{project_id}` | `project:update` |
| DELETE | `/orgs/{org_id}/projects/{project_id}` | `project:delete` |

---

## 4. Queues (7 routes) — `app/routers/queues.py`

| Method | Path | Permission | Description |
|---|---|---|---|
| GET | `/projects/{id}/queues` | `queue:read` | List queues with live stats |
| POST | `/projects/{id}/queues` | `queue:create` | Create a queue |
| GET | `/projects/{id}/queues/{qid}` | `queue:read` | Queue detail + stats + rate-limit status |
| PATCH | `/projects/{id}/queues/{qid}` | `queue:update` | Update concurrency/priority/retry policy/rate limits/`shard_count` (changing `shard_count` auto-triggers a rebalance) |
| DELETE | `/projects/{id}/queues/{qid}` | `queue:delete` | Soft-delete |
| POST | `/projects/{id}/queues/{qid}/pause` | `queue:pause` | Stop workers claiming from this queue |
| POST | `/projects/{id}/queues/{qid}/resume` | `queue:pause` | Resume claiming |

**Example — queue detail response (abbreviated)**
```json
{ "data": {
    "id": "...", "name": "payments", "shard_count": 4,
    "rate_limit_per_minute": 60, "rate_limit_burst": 60,
    "stats": { "pending_count": 12, "running_count": 3, "failed_count": 0, "throughput_per_min": 8 },
    "rate_limit_status": { "limit_per_minute": 60, "burst_capacity": 60, "tokens_remaining": 24.7, "is_rate_limited": false }
} }
```

---

## 5. Jobs (11 routes) — `app/routers/jobs.py`

| Method | Path | Permission | Description |
|---|---|---|---|
| POST | `/queues/{queue_id}/jobs` | `job:create` | Create a job (any of the 5 job types) |
| GET | `/queues/{queue_id}/jobs` | `job:read` | List jobs (filter by status/type/tag) |
| GET | `/jobs/{job_id}` | `job:read` | Full detail incl. payload, executions, logs |
| DELETE | `/jobs/{job_id}` | `job:cancel` | Cancel a queued/scheduled/blocked job |
| POST | `/jobs/{job_id}/retry` | `job:retry` | Requeue a failed/dead job, clears DLQ entry |
| GET | `/jobs/{job_id}/logs` | `job:view_logs` | Paginated log stream |
| POST | `/jobs/batch-cancel` | `job:cancel` | Cancel many queued jobs by ID in one call |
| GET | `/jobs/{job_id}/dependencies` | `workflow:read` | Full recursive DAG (ancestors + descendants) + workflow progress |
| GET | `/jobs/{job_id}/dependents` | `workflow:read` | Direct (one-hop) dependents only |
| POST | `/jobs/{job_id}/dependencies` | `workflow:create` | Add a dependency to an existing job (cycle-checked) |
| DELETE | `/jobs/{job_id}/dependencies/{dep_job_id}` | `workflow:create` | Remove a dependency (auto-unblocks if it was the last one) |

**Example — create an immediate job**
```json
POST /queues/{queue_id}/jobs
{ "name": "charge-card", "job_type": "immediate", "payload": { "order_id": "4521" } }
```

**Example — create a recurring job**
```json
{ "name": "nightly-report", "job_type": "recurring", "cron_expression": "0 2 * * *", "payload": {} }
```

**Example — create a batch job (parent + children in one call)**
```json
{ "name": "bulk-import", "job_type": "batch",
  "batch_jobs": [{ "name": "import-row-1", "payload": {} }, { "name": "import-row-2", "payload": {} }] }
```

---

## 6. Workflows (1 route) — `app/routers/jobs.py`

| Method | Path | Permission | Description |
|---|---|---|---|
| POST | `/workflows` | `workflow:create` | Atomically create N jobs + a dependency graph in one call, using local `ref` strings instead of real UUIDs |

**Example — diamond workflow (A → B, A → C, B + C → D)**
```json
POST /workflows
{ "name": "order-fulfillment",
  "jobs": [
    { "ref": "charge-card", "name": "charge-card", "queue_id": "..." },
    { "ref": "send-receipt", "name": "send-receipt", "queue_id": "...", "depends_on": ["charge-card"] },
    { "ref": "update-ledger", "name": "update-ledger", "queue_id": "...", "depends_on": ["charge-card"] },
    { "ref": "close-order", "name": "close-order", "queue_id": "...", "depends_on": ["send-receipt", "update-ledger"] }
  ] }
```
Response maps each `ref` to its real UUID and initial status (`queued` for
the root, `blocked` for everything downstream), plus a `dependency_map`. A
cycle anywhere in the payload is rejected before any row is written
(`WORKFLOW_CYCLE_DETECTED`, validated in-memory via Kahn's algorithm — no DB
round trip needed since the whole graph is self-contained in the request).

---

## 7. Workers (3 routes) — `app/routers/workers.py`

| Method | Path | Permission | Description |
|---|---|---|---|
| GET | `/workers` | `worker:read` | List workers with live status |
| GET | `/workers/{worker_id}` | `worker:read` | Detail + heartbeat history |
| DELETE | `/workers/{worker_id}` | `worker:force_offline` | Force a worker offline |

---

## 8. Dead Letter Queue (5 routes) — `app/routers/dead_letter_queue.py`

| Method | Path | Permission | Description |
|---|---|---|---|
| GET | `/dead-letter-queue` | `dlq:read` | List DLQ entries (filter by `queue_id`, `job_id`, `is_resolved`) |
| POST | `/dead-letter-queue/{id}/resolve` | `dlq:resolve` | Mark resolved (audit trail: who, when) |
| POST | `/dead-letter-queue/{id}/replay` | `dlq:replay` | Requeue the underlying job |
| GET | `/dead-letter-queue/{id}/analysis` | `dlq:read` | AI summary + error classification + execution pattern |
| POST | `/dead-letter-queue/{id}/reanalyze` | `dlq:resolve` | Force-regenerate the AI summary (202 Accepted, fire-and-forget) |

**Example — analysis response**
```json
{ "data": {
    "dlq_id": "...", "job_name": "charge-card", "error_type": "Network/Infrastructure",
    "ai_summary": "**Root Cause** ...", "is_generating": false,
    "total_attempts": 3, "time_to_failure_ms": 4521,
    "execution_pattern": { "attempts": 3, "avg_duration_ms": 4521, "min_duration_ms": 1203, "max_duration_ms": 8901, "failed_consistently": true }
} }
```

---

## 9. Sharding (2 routes) — `app/routers/shards.py`

| Method | Path | Permission | Description |
|---|---|---|---|
| GET | `/queues/{queue_id}/shards` | `queue:read` | Per-shard worker assignment + pending/running counts + a recommendation (`optimal`/`add_workers`/`reduce_shards`) |
| POST | `/queues/{queue_id}/shards/rebalance` | `queue:configure` | Clear the shard registry, forcing all workers to re-assign within ~15s |

## 10. Failure Patterns (1 route) — `app/routers/shards.py`

| Method | Path | Permission | Description |
|---|---|---|---|
| GET | `/queues/{queue_id}/failure-patterns` | `dlq:read` | Queue-level failure analytics over the last 100 DLQ entries — error-type distribution, peak UTC failure hour, trend, one-sentence recommendation. Pure analytics, no AI call; cached in Redis 5 min. |

---

## 11. Retry Policies (4 routes) — `app/routers/retry_policies.py`

| Method | Path |
|---|---|
| GET | `/retry-policies` |
| POST | `/retry-policies` |
| GET | `/retry-policies/{policy_id}` |
| PATCH | `/retry-policies/{policy_id}` |

---

## WebSocket

`GET /ws/connect?token=<jwt>` — one connection per browser tab, org-scoped
fan-out. 15 event types are sent over the wire, each wrapped in the envelope
`{ "event": "...", "data": {...}, "ts": "..." }`: two connection-lifecycle
messages sent directly on connect (`connection.established`, `snapshot`), plus
13 domain events fanned out through Redis pub/sub:

`job.claimed`, `job.running`, `job.completed`, `job.failed`, `job.dead`,
`job.unblocked`, `worker.connected`, `worker.disconnected`,
`worker.heartbeat`, `queue.stats`, `queue.rate_limited`,
`queue.rebalancing`, `dlq.ai_summary_ready`.
