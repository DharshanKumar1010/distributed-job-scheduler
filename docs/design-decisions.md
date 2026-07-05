# Design Decisions

Six decisions where a real alternative was available and a deliberate call
was made. Each is written the way I'd defend it in a design review: what we
chose, why, and what it costs us.

---

## 1. PostgreSQL `SKIP LOCKED` as the job queue — not a dedicated broker

Rather than introducing Celery + RabbitMQ, BullMQ + Redis, or a hosted
queue (SQS), all job queueing runs directly in PostgreSQL. The critical
insight is that **job state and job data must be consistent** — an external
broker creates a window where a job can be dequeued from the broker but its
row in the database hasn't caught up yet, which is exactly where
phantom-job and duplicate-processing bugs come from in production systems.

```sql
UPDATE jobs
SET status = 'claimed', worker_id = :worker_id,
    claimed_at = now(), attempts = attempts + 1
WHERE id = (
  SELECT id FROM jobs
  WHERE queue_id = :queue_id AND status = 'queued'
    AND (scheduled_at IS NULL OR scheduled_at <= now())
  ORDER BY priority DESC, created_at ASC
  FOR UPDATE SKIP LOCKED         -- prevents two workers claiming the same job
  LIMIT 1
)
RETURNING *;
```

`FOR UPDATE SKIP LOCKED` means: lock the winning row, and if any other
transaction already has a candidate row locked, skip it instead of blocking.
N workers can run this exact query concurrently against the same queue and
each one gets a *different* job, atomically, with no application-level
mutex, no distributed lock, and no broker acknowledgement protocol.

| ✓ Why we chose this | ⚠ Trade-off |
|---|---|
| Zero additional broker dependency to run, monitor, or upgrade | Postgres is now both the system of record *and* the queue — its write throughput is the ceiling |
| Claim and state update are the same atomic statement — no ack/nack protocol to get wrong | At very high throughput (>50k jobs/sec) a dedicated broker with in-memory queueing wins |
| Debuggable with `psql` — no special tooling to inspect "what's actually queued" | Long-poll workers still hit the DB every second even when idle (mitigated by low `WORKER_POLL_INTERVAL_SECONDS` cost in practice) |
| Verified correct with real concurrency tests, not mocks (`test_concurrent_workers_claim_same_job_exactly_once`) | |

---

## 2. Visibility timeout + reaper — not pessimistic locking for the job's full runtime

Workers don't hold a database lock for as long as a job takes to run. They
mark `status='claimed'`, release the row lock immediately (the `UPDATE`
commits), and heartbeat separately every 10 seconds. A **reaper** process
runs every 30 seconds, finds workers whose `last_seen` is older than 45
seconds, marks them `offline`, and resets anything they had
`claimed`/`running` back to `queued`. This is the same pattern SQS and
Celery use in production.

| ✓ Why we chose this | ⚠ Trade-off |
|---|---|
| No long-held locks — a slow job can't cascade into lock contention for the whole queue | At-least-once delivery: a job can be reclaimed and re-run, so handlers must be idempotent |
| Worker crashes recover automatically — no manual "who owns this job" cleanup | Up to 45 seconds before a genuinely dead worker's jobs are noticed and reclaimed |
| The same mechanism scales to N worker processes with zero coordination between them | The reaper itself is not sharded — it's cheap enough (`UPDATE ... WHERE last_seen < cutoff`) not to need it |

---

## 3. DAG engine on a recursive CTE — not application-level graph traversal

Workflow dependencies (Phase 8) are resolved with a recursive CTE in
Postgres rather than walking the graph node-by-node in Python. One query
fetches the entire ancestor or descendant tree regardless of depth (capped
at 20 levels as a runaway-query guard), instead of N+1 round trips.
Unblocking chains (`check_and_unblock`) recurses through `asyncio.gather`
so a diamond-shaped fan-in resolves both arms concurrently, each in its own
isolated DB session (a single `AsyncSession` can't be driven from two
coroutines at once).

Cycle detection is the one place that's deliberately *not* SQL: it's an
**iterative** DFS in Python (an explicit stack, not recursive function
calls), specifically to avoid Python's recursion limit on adversarial or
very deep graphs, and it returns the actual cycle path (job names, not just
UUIDs) so the API error is actually actionable.

| ✓ Why we chose this | ⚠ Trade-off |
|---|---|
| O(1) round trips regardless of graph depth | Recursive CTEs have a hard 20-level depth guard — deeper graphs are truncated, not rejected |
| Fan-in/fan-out unblocking parallelizes naturally via `asyncio.gather` | Parallel branches need isolated sessions — one more thing to get right per recursive call |
| Cycle detection never stack-overflows, and tells you *which* jobs form the cycle | An iterative DFS is more code than a five-line recursive one |

---

## 4. Redis sliding-window + token bucket — two different rate limiters for two different problems

Phase 9 needed rate limiting at two layers that look similar but aren't:
**API abuse prevention** (a user hammering the REST API) and **downstream
protection** (a queue's jobs hitting a fragile third-party service too
fast). These get two different algorithms, both implemented as atomic Redis
Lua scripts so concurrent requests can never both slip through:

- **Sliding window** (API middleware): a Redis sorted set per
  `(user, endpoint-group)`, pruned to the trailing 60s on every check. Exact
  request counting, no burst allowance — appropriate for "don't let one user
  starve the API."
- **Token bucket** (per-queue execution): capacity + refill rate, checked by
  the worker *before* executing a claimed job. Allows short bursts up to
  `rate_limit_burst`, which is what you actually want for "don't call this
  payment gateway more than 60 times/minute, but let a 5-job burst through
  since jobs don't arrive perfectly evenly."

| ✓ Why we chose this | ⚠ Trade-off |
|---|---|
| Lua scripts make check-and-increment atomic — no race between concurrent requests double-spending the same slot | Two algorithms to maintain instead of one, because they solve genuinely different problems |
| Token bucket naturally supports bursts; sliding window naturally doesn't allow starvation | A rate-limited job is un-claimed (status back to `queued`, `attempts` decremented) rather than failed — correct, but one more state transition to reason about |
| Both verified under real `asyncio.gather` concurrency in tests, not single-threaded assumptions | |

---

## 5. Consistent hashing over a Redis-backed worker registry — not a fixed hash ring

Queue sharding (Phase 10) needed workers to self-assign to shards without a
central coordinator. Each worker periodically registers itself in a Redis
sorted set (`shard:workers:{queue_id}`, score = last-seen timestamp); its
shard is simply its **lexicographic position** among currently-active
workers, mod `shard_count`. Claiming adds
`(hashtext(id::text) % shard_count)` to the existing `SKIP LOCKED` query.

This was also where a real correctness bug surfaced and got fixed before
shipping: Postgres's `%` operator follows the sign of the *dividend*, so
`hashtext()` (which can be negative) produces negative results roughly half
the time. Naively used, that would silently strand ~50% of jobs on no
shard at all. The fix is normalizing with
`(((hashtext(id::text) % n) + n) % n)` everywhere the expression appears.

| ✓ Why we chose this | ⚠ Trade-off |
|---|---|
| No coordinator, no fixed ring to rebalance by hand — assignments reshuffle automatically as workers join/leave | A worker that just joined mid-rollout gets a transient assignment until the *next* re-registration pass converges everyone |
| `shard_count` can change live — a PATCH triggers a rebalance, workers pick it up within one heartbeat cycle | If workers < shards, some shards simply have no owner (surfaced explicitly as `add_workers` recommendation, not silently dropped) |
| One worker never "covers" a departed peer's shard automatically — no silent double-duty | This is a deliberate trade-off, not an oversight: verified explicitly by `test_worker_leave_does_not_let_survivor_steal_other_shard` |

---

## 6. Fire-and-forget AI analysis — never on the request/execution path

Phase 12's Groq-powered failure analysis is wired so it can **never**
affect job processing or API latency: the worker calls
`asyncio.create_task(ai_service.run_dlq_analysis(...))` and immediately
continues to publish `job.dead` — the task is never awaited. If
`GROQ_API_KEY` isn't configured, `generate_failure_summary` detects
that up front and returns a fully-structured static analysis (built from
the same error-classification heuristics used everywhere else) without
attempting a network call at all. If the API call itself fails for any
reason, a separate exception handler writes `[Analysis unavailable: ...]`
instead of leaving the field null forever.

| ✓ Why we chose this | ⚠ Trade-off |
|---|---|
| A slow or down Groq API can never block a worker's poll loop or an API response | The DLQ entry briefly shows "generating" — the frontend polls/WS-updates rather than getting the summary synchronously |
| Two distinct, honest fallback states (no key vs. call failed) instead of one generic error string | Reanalyze is a genuinely separate code path (`ai_summary = NULL` + re-trigger), not just "call the same function again" |
| The feature degrades to something still useful (heuristic classification + generic advice) instead of a blank UI | |
