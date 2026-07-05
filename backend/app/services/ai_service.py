import json
import logging
import uuid
from collections import Counter
from datetime import timezone

from groq import AsyncGroq
from redis.asyncio import Redis
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.dead_letter_queue import DeadLetterQueueEntry
from app.models.job import Job
from app.models.job_execution import JobExecution
from app.models.job_log import JobLog
from app.models.queue import Queue
from app.websocket.publisher import publish_event

logger = logging.getLogger("ai_service")

MODEL = "llama-3.3-70b-versatile"
MAX_TOKENS = 400
FAILURE_PATTERN_CACHE_SECONDS = 300
FAILURE_PATTERN_SAMPLE_SIZE = 100

GENERIC_ADVICE: dict[str, str] = {
    "Network/Infrastructure": "verify the downstream service is reachable and check network/firewall config",
    "Authorization": "verify credentials/tokens are valid and have not expired",
    "Data/Logic": "check the job payload shape matches what the handler expects",
    "Rate Limiting": "add backoff/jitter or reduce request volume to the downstream service",
    "Resource Exhaustion": "check memory/CPU limits and payload size",
    "Code Bug": "review the handler code path for the given payload",
    "Data Conflict": "check for race conditions or duplicate submissions",
    "Unknown": "review the full traceback and recent logs for more context",
}


def extract_error_type(error_message: str | None) -> str:
    """Heuristic classifier - no ML, just string matching."""
    if not error_message:
        return "Unknown"
    text = error_message.lower()

    if "connection refused" in text or "timeout" in text or "timed out" in text:
        return "Network/Infrastructure"
    if "permission denied" in text or "unauthorized" in text or "403" in text:
        return "Authorization"
    if (
        "not found" in text
        or "404" in text
        or "keyerror" in text
        or "attributeerror" in text
    ):
        return "Data/Logic"
    if "rate limit" in text or "429" in text or "too many requests" in text:
        return "Rate Limiting"
    if "out of memory" in text or "memoryerror" in text:
        return "Resource Exhaustion"
    if "syntaxerror" in text or "typeerror" in text or "valueerror" in text:
        return "Code Bug"
    if "duplicate" in text or "unique constraint" in text:
        return "Data Conflict"
    return "Unknown"


def format_execution_history(executions: list[JobExecution]) -> str:
    if not executions:
        return "No execution history available"
    lines = []
    for execution in executions:
        started = (
            execution.started_at.isoformat() if execution.started_at else "unknown"
        )
        duration = execution.duration_ms if execution.duration_ms is not None else "?"
        error = (execution.error_message or "")[:100]
        lines.append(
            f"Attempt {execution.attempt_number}: started {started}, "
            f"failed after {duration}ms — {error}"
        )
    return "\n".join(lines)


def format_logs(logs: list[JobLog]) -> str:
    if not logs:
        return "No logs available"
    lines = []
    for log in logs[:20]:
        ts = log.timestamp.strftime("%H:%M:%S") if log.timestamp else "??:??:??"
        level = log.level.value.upper().ljust(5)
        lines.append(f"[{level} {ts}] {log.message}")
    return "\n".join(lines)


def _is_api_key_configured() -> bool:
    key = settings.GROQ_API_KEY
    return bool(key) and key != "gsk_..."


def _static_fallback_summary(error_type: str, dlq_entry: DeadLetterQueueEntry) -> str:
    advice = GENERIC_ADVICE.get(error_type, GENERIC_ADVICE["Unknown"])
    error_message = (dlq_entry.last_error or "")[:200]
    return (
        f"Automated analysis (AI unavailable): {error_type} error detected after "
        f"{dlq_entry.total_attempts} attempts. Last error: {error_message}. "
        f"Check: {advice}"
    )


async def generate_failure_summary(
    job: Job,
    dlq_entry: DeadLetterQueueEntry,
    execution_history: list[JobExecution],
    recent_logs: list[JobLog],
    queue_name: str = "unknown",
) -> str:
    error_type = extract_error_type(dlq_entry.last_error)

    if not _is_api_key_configured():
        return _static_fallback_summary(error_type, dlq_entry)

    time_to_failure = dlq_entry.failed_at - job.created_at

    prompt = f"""You are an expert distributed systems debugger analyzing a failed background job in a production job scheduler.

## Job Information
- Name: {job.name}
- Type: {job.job_type.value if hasattr(job.job_type, "value") else job.job_type}
- Queue: {queue_name}
- Total attempts: {dlq_entry.total_attempts}
- First attempt: {job.created_at.isoformat()}
- Final failure: {dlq_entry.failed_at.isoformat()}
- Time to final failure: {time_to_failure}

## Job Payload
{json.dumps(job.payload, indent=2, default=str)}

## Execution History ({len(execution_history)} attempts)
{format_execution_history(execution_history)}

## Error Pattern Analysis
Last error type: {error_type}
Last error message: {dlq_entry.last_error}

## Full Error Traceback (last attempt)
{dlq_entry.last_traceback or "No traceback available"}

## Recent Logs
{format_logs(recent_logs)}

## Your Analysis Task
Provide a concise debugging report with these exact sections:

**Root Cause** (1-2 sentences): What specifically caused this failure?

**Error Pattern** (1 sentence): Is this a transient error, a bug, a configuration issue, or a data problem?

**Immediate Fix** (2-3 bullet points): What should a developer check or change right now?

**Prevention** (1-2 bullet points): How to prevent this class of failure in future jobs?

Be specific to this job's payload and error — no generic advice.
If the payload contains sensitive-looking fields (password, token, secret, key), note them but do not include their values in your analysis."""

    client = AsyncGroq(api_key=settings.GROQ_API_KEY)
    message = await client.chat.completions.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.choices[0].message.content


async def run_dlq_analysis(
    dlq_id: uuid.UUID,
    job_id: uuid.UUID,
    redis: Redis | None,
    org_id: uuid.UUID | None,
) -> None:
    """Generates (or regenerates) the AI summary for one DLQ entry and
    publishes a WS event when done. Meant to be scheduled via
    asyncio.create_task() - never awaited directly by request/job-processing
    code, so a slow or failing AI call can never block job execution or an
    API response.
    """
    async with AsyncSessionLocal() as db:
        dlq_entry = await db.get(DeadLetterQueueEntry, dlq_id)
        job = await db.get(Job, job_id)
        if dlq_entry is None or job is None:
            return

        queue = await db.get(Queue, dlq_entry.queue_id)
        queue_name = queue.name if queue else "unknown"

        executions = list(
            (
                await db.execute(
                    select(JobExecution)
                    .where(JobExecution.job_id == job_id)
                    .order_by(JobExecution.attempt_number.asc())
                )
            )
            .scalars()
            .all()
        )
        logs = list(
            (
                await db.execute(
                    select(JobLog)
                    .where(JobLog.job_id == job_id)
                    .order_by(JobLog.timestamp.desc())
                    .limit(20)
                )
            )
            .scalars()
            .all()
        )

        try:
            summary = await generate_failure_summary(
                job, dlq_entry, executions, logs, queue_name
            )
        except Exception as exc:  # noqa: BLE001 - AI failures must never propagate
            logger.warning("AI summary generation failed: %s", exc)
            summary = f"[Analysis unavailable: {type(exc).__name__}]"

        await db.execute(
            update(DeadLetterQueueEntry)
            .where(DeadLetterQueueEntry.id == dlq_id)
            .values(ai_summary=summary)
        )
        await db.commit()
        job_name = job.name

    if redis is not None and org_id is not None:
        try:
            await publish_event(
                redis,
                org_id,
                "dlq.ai_summary_ready",
                {"dlq_id": str(dlq_id), "job_id": str(job_id), "job_name": job_name},
            )
        except Exception:
            logger.exception("Failed to publish dlq.ai_summary_ready for %s", dlq_id)


def _trend_note(trend: str) -> str:
    return {
        "increasing": "Failures are trending up — investigate soon.",
        "decreasing": "Failures are trending down.",
        "stable": "Failure rate is stable.",
    }[trend]


def _recommendation_for(most_common_error: str, trend: str) -> str:
    advice = GENERIC_ADVICE.get(most_common_error, GENERIC_ADVICE["Unknown"])
    return f"{_trend_note(trend)} Most failures are {most_common_error} — {advice}."


async def analyze_failure_pattern(
    queue_id: uuid.UUID, db: AsyncSession, redis: Redis | None
) -> dict:
    """Pure analytics over existing DLQ data - no AI call."""
    cache_key = f"failpat:{queue_id}"
    if redis is not None:
        cached = await redis.get(cache_key)
        if cached:
            return json.loads(cached)

    result = await db.execute(
        select(DeadLetterQueueEntry)
        .where(DeadLetterQueueEntry.queue_id == queue_id)
        .order_by(DeadLetterQueueEntry.created_at.desc())
        .limit(FAILURE_PATTERN_SAMPLE_SIZE)
    )
    entries = list(result.scalars().all())

    total_failures = len(entries)
    error_types = [extract_error_type(e.last_error) for e in entries]
    distribution = dict(Counter(error_types))
    most_common_error = (
        max(distribution, key=distribution.get) if distribution else "None"
    )

    hour_counts = Counter(e.failed_at.astimezone(timezone.utc).hour for e in entries)
    peak_failure_hour = max(hour_counts, key=hour_counts.get) if hour_counts else None

    trend = "stable"
    if total_failures >= 10:
        timestamps = sorted(e.created_at for e in entries)
        earliest, latest = timestamps[0], timestamps[-1]
        span_seconds = (latest - earliest).total_seconds()
        if span_seconds > 0:
            midpoint = earliest + (latest - earliest) / 2
            older_count = sum(1 for t in timestamps if t < midpoint)
            newer_count = sum(1 for t in timestamps if t >= midpoint)
            if newer_count > older_count * 1.2:
                trend = "increasing"
            elif newer_count < older_count * 0.8:
                trend = "decreasing"

    payload = {
        "total_failures": total_failures,
        "error_type_distribution": distribution,
        "most_common_error": most_common_error,
        "failure_rate_trend": trend,
        "peak_failure_hour": peak_failure_hour,
        "recommendation": _recommendation_for(most_common_error, trend),
    }

    if redis is not None:
        await redis.set(
            cache_key, json.dumps(payload), ex=FAILURE_PATTERN_CACHE_SECONDS
        )

    return payload
