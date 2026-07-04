from datetime import datetime, timedelta


def compute_next_run(strategy: str, base_delay: int, attempt: int) -> datetime:
    if strategy == "fixed":
        delta = base_delay
    elif strategy == "linear":
        delta = base_delay * attempt
    elif strategy == "exponential":
        delta = base_delay * (2 ** (attempt - 1))
    return datetime.utcnow() + timedelta(seconds=delta)
