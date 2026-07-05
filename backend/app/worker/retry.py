from datetime import datetime, timedelta


def compute_next_run(
    strategy: str, base_delay: int, attempt: int, max_delay: int
) -> datetime:
    if strategy == "fixed":
        delta = base_delay
    elif strategy == "linear":
        delta = base_delay * attempt
    elif strategy == "exponential":
        delta = base_delay * (2 ** (attempt - 1))
    else:
        delta = base_delay
    delta = min(delta, max_delay)
    return datetime.utcnow() + timedelta(seconds=delta)
