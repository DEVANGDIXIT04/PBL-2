"""Small in-memory rate limiter for authentication routes."""

from collections import defaultdict, deque
from time import monotonic

from fastapi import HTTPException, Request

from app.core.config import get_settings

_hits: dict[str, deque[float]] = defaultdict(deque)


def enforce_rate_limit(
    key: str,
    *,
    limit: int,
    window_seconds: int,
    enabled: bool = True,
) -> None:
    """Reject the caller once they exceed `limit` hits inside the window."""
    if not enabled:
        return
    now = monotonic()
    bucket = _hits[key]
    while bucket and now - bucket[0] > window_seconds:
        bucket.popleft()
    if len(bucket) >= limit:
        raise HTTPException(status_code=429, detail="Too many requests. Try again shortly.")
    bucket.append(now)


def limit_auth(request: Request) -> None:
    """Apply the configured auth rate limit, keyed by client host."""
    settings = get_settings()
    host = request.client.host if request.client else "unknown"
    enforce_rate_limit(
        f"auth:{host}",
        limit=settings.rate_limit_auth,
        window_seconds=settings.rate_limit_window_seconds,
        enabled=settings.rate_limit_enabled,
    )


def reset_rate_limits() -> None:
    """Clear counters. Used by tests."""
    _hits.clear()
