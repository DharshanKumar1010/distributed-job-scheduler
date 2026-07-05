# Entity-Relationship Diagram

All 13 tables, as they exist in the Alembic-managed schema
(`backend/alembic/versions/`). Every table also carries `created_at` /
`updated_at` via a shared `TimestampMixin`, omitted below for readability.

```mermaid
erDiagram
    ORGANIZATIONS ||--o{ USERS : "employs"
    ORGANIZATIONS ||--o{ PROJECTS : "owns"
    PROJECTS ||--o{ QUEUES : "contains"
    RETRY_POLICIES ||--o{ QUEUES : "default for"
    QUEUES ||--o{ WORKERS : "polled by"
    QUEUES ||--o{ JOBS : "holds"
    QUEUES ||--o{ DEAD_LETTER_QUEUE_ENTRIES : "scoped to"
    WORKERS ||--o{ WORKER_HEARTBEATS : "reports"
    WORKERS ||--o{ JOBS : "claims"
    WORKERS ||--o{ JOB_EXECUTIONS : "runs"
    JOBS ||--o{ JOB_EXECUTIONS : "attempted as"
    JOBS ||--o{ JOB_LOGS : "logs"
    JOBS ||--o| SCHEDULED_JOBS : "recurs via"
    JOBS ||--o{ DEAD_LETTER_QUEUE_ENTRIES : "dies into"
    JOBS ||--o{ JOB_DEPENDENCIES : "depends (job_id)"
    JOBS ||--o{ JOB_DEPENDENCIES : "blocks (depends_on_job_id)"
    JOBS ||--o{ JOBS : "batch parent/child"
    JOB_EXECUTIONS ||--o{ JOB_LOGS : "attributed to"
    USERS ||--o{ DEAD_LETTER_QUEUE_ENTRIES : "resolves"

    ORGANIZATIONS {
        uuid id PK
        string name
        string slug UK
        string plan
        bool is_active
    }

    USERS {
        uuid id PK
        uuid org_id FK
        string email UK
        string hashed_password
        string full_name
        enum role "owner/admin/member/viewer"
        bool is_active
    }

    PROJECTS {
        uuid id PK
        uuid org_id FK
        string name
        string slug "UK with org_id"
        string description
        bool is_active
    }

    RETRY_POLICIES {
        uuid id PK
        string name
        int max_attempts
        enum strategy "fixed/linear/exponential"
        int base_delay_seconds
        int max_delay_seconds
        bool is_default
    }

    QUEUES {
        uuid id PK
        uuid project_id FK
        string name
        string slug "UK with project_id"
        int priority
        int concurrency_limit
        uuid retry_policy_id FK
        bool is_paused
        bool is_active
        int shard_count "1-64"
        int rate_limit_per_minute
        int rate_limit_burst
    }

    WORKERS {
        uuid id PK
        uuid queue_id FK
        string hostname
        int pid
        enum status "idle/busy/offline"
        int max_concurrency
        int current_jobs
        timestamptz last_seen
        json metadata
    }

    WORKER_HEARTBEATS {
        uuid id PK
        uuid worker_id FK
        timestamptz ts
        float cpu_pct
        float mem_pct
        int active_job_count
    }

    JOBS {
        uuid id PK
        uuid queue_id FK
        uuid parent_job_id FK "self, batch"
        string idempotency_key UK
        string name
        json payload
        enum status "queued/scheduled/claimed/running/completed/failed/dead/cancelled/blocked"
        int priority
        enum job_type "immediate/delayed/scheduled/recurring/batch"
        string cron_expression
        timestamptz scheduled_at
        timestamptz run_at
        int attempts
        int max_attempts
        string retry_strategy
        int base_delay_seconds
        int max_delay_seconds
        uuid worker_id FK
        timestamptz claimed_at
        timestamptz started_at
        timestamptz completed_at
        timestamptz failed_at
        json result
        string error_message
        text error_traceback
        json tags
    }

    JOB_EXECUTIONS {
        uuid id PK
        uuid job_id FK
        uuid worker_id FK
        int attempt_number
        enum status
        timestamptz started_at
        timestamptz completed_at
        int duration_ms
        string error_message
        text error_traceback
        json result
    }

    JOB_LOGS {
        uuid id PK
        uuid job_id FK
        uuid execution_id FK
        enum level "debug/info/warning/error"
        text message
        timestamptz timestamp
        json metadata
    }

    SCHEDULED_JOBS {
        uuid id PK
        uuid job_id FK "the recurring template"
        timestamptz next_run_at
        timestamptz last_run_at
        string cron_expression
        bool is_active
        string timezone
    }

    DEAD_LETTER_QUEUE_ENTRIES {
        uuid id PK
        uuid job_id FK
        uuid queue_id FK
        timestamptz failed_at
        int total_attempts
        text last_error
        text last_traceback
        text ai_summary
        bool is_resolved
        timestamptz resolved_at
        uuid resolved_by FK "-> users.id"
    }

    JOB_DEPENDENCIES {
        uuid job_id FK "UK with depends_on_job_id"
        uuid depends_on_job_id FK
    }
```

## Indexing notes

The single most important index in the schema is the compound index behind
the atomic claim query:

```sql
CREATE INDEX ix_jobs_claim_query
  ON jobs (queue_id, status, priority DESC, created_at ASC);
```

Every other index exists to support a specific hot-path query rather than
"just in case":

| Index | Serves |
|---|---|
| `ix_jobs_claim_query` (`queue_id, status, priority DESC, created_at`) | The claim query's `WHERE queue_id = ... AND status = 'queued' ORDER BY priority DESC, created_at ASC` |
| `ix_jobs_status` | Dashboard/queue aggregate counts (`COUNT(*) FILTER (WHERE status = ...)`) |
| `ix_jobs_scheduled_at` | Dispatcher's materializer scan (`WHERE status='scheduled' AND scheduled_at <= now()`) |
| `ix_jobs_worker_id` | Reaper's "what did this dead worker have claimed" lookup |
| `ix_worker_heartbeats_ts` | Heartbeat history queries (latest N per worker) |
| `ix_job_executions_job_id_attempt_number` | Execution history ordered by attempt |
| `ix_job_logs_timestamp` | Recent-logs queries (including the AI prompt's log window) |
| `ix_scheduled_jobs_next_run_at` | Cron scheduler's due-template scan |
| `ix_projects_org_id_slug` / `ix_queues_project_id_slug` (unique) | Slug uniqueness scoped to parent, not global |
