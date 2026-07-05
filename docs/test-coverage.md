# Test Coverage

All 33 tests run against a **real PostgreSQL + Redis instance** — nothing in
the suite mocks the database, Redis, or the job-claiming logic itself. The
suite covers unit logic, cross-service integration, real HTTP requests
(via `httpx.ASGITransport`), and genuine `asyncio.gather` concurrency.

```
$ pytest tests/ -v --tb=short
================================ 33 passed in ~18s ================================
```

| File | Tests | Category | What it proves |
|---|---|---|---|
| `test_retry.py` | 8 | Unit | All 3 backoff strategies (fixed/linear/exponential) compute correct delays, and each respects `max_delay_seconds` as a cap |
| `test_worker.py` | 4 | Concurrency | `SKIP LOCKED` claim exclusivity, DLQ insertion after exhausted retries, reaper recovery of a stale worker's jobs, and the actual 2-worker race condition |
| `test_dependencies.py` | 6 | Integration | Linear chain, fan-in, fan-out, diamond unblocking, iterative cycle detection with correct path, and atomic `POST /workflows` creation |
| `test_rate_limiting.py` | 5 | Concurrency | Sliding-window limit + 429 headers, window expiry, token-bucket burst + refill, Lua-script atomicity under `asyncio.gather`, cross-dispatcher cron dedup |
| `test_rbac.py` | 6 | Security | All 4 roles' boundaries, admin's owner-promotion block, owner's full authority, and cross-org isolation regardless of role |
| `test_sharding.py` | 4 | Distribution | `shard_count=1` backward compatibility, 3-worker/3-shard disjoint partitioning, single-worker partial coverage, and the worker-leave-doesn't-steal invariant |

---

## Most important test: concurrent job claiming

This is the test that proves the single most load-bearing guarantee in the
whole system — that `FOR UPDATE SKIP LOCKED` actually does what it's
supposed to do under real concurrency, not just in theory.

```python
async def test_concurrent_workers_claim_same_job_exactly_once(test_queue):
    job = await _create_job(test_queue, payload={"handler": "noop"})

    worker_a = await _make_job_worker(test_queue)
    worker_b = await _make_job_worker(test_queue)

    # Both workers poll at the same instant - this is the race.
    await asyncio.gather(worker_a._poll_once(), worker_b._poll_once())

    claimed_by = [w for w in (worker_a, worker_b) if job.id in w.active_tasks]
    assert len(claimed_by) == 1        # exactly one worker claimed it

    await asyncio.gather(*claimed_by[0].active_tasks.values())

    executions = await db.execute(
        select(JobExecution).where(JobExecution.job_id == job.id)
    )
    assert len(executions.all()) == 1  # exactly one execution row - no duplicate run
```

Two independent `JobWorker` instances, backed by two independent database
connections, call the real claim query at the same moment via
`asyncio.gather`. If `SKIP LOCKED` didn't work, this test would be flaky —
it isn't, because Postgres row-level locking makes the outcome
deterministic regardless of how the coroutines happen to interleave.

---

## Notable test-infrastructure decisions

- **Session-scoped event loop.** `pytest-asyncio` is configured with
  `asyncio_default_fixture_loop_scope = session` — a function-scoped loop
  caused `InterfaceError: another operation is in progress` against the
  shared async engine. This was a real failure encountered early and fixed
  once, project-wide.
- **Real HTTP for RBAC.** `test_rbac.py` uses `httpx.AsyncClient` with
  `ASGITransport(app=app)` to exercise actual routes end-to-end (login →
  bearer token → real permission-gated request), rather than calling
  service functions directly — permission enforcement lives in the
  dependency-injection layer, so it has to be tested at the HTTP boundary
  to mean anything. `ASGITransport` skips the app's lifespan, so
  `app.state.redis_client` has to be provided directly in the test setup.
- **Deterministic time in rate-limit tests.** Both the sliding-window and
  token-bucket Lua scripts accept an optional injected `now`, so the
  window-expiry test simulates 60 seconds passing without a real 60-second
  sleep.
- **Convergence-aware sharding tests.** A worker's shard assignment depends
  on which *other* workers are currently registered — so tests register all
  workers first, then do a second `assign_shard` pass per worker to read
  back each one's converged (stable) assignment, mirroring how production
  workers self-correct on their next periodic re-registration.
