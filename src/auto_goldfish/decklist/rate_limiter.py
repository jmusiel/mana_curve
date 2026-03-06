"""Thread-safe per-service rate limiter for external API calls."""

from __future__ import annotations

import threading
import time

# Default minimum intervals (seconds) between requests per service.
DEFAULT_INTERVALS: dict[str, float] = {
    "scryfall": 0.1,    # Scryfall asks for 50-100ms between requests
    "archidekt": 0.5,   # Politeness
    "moxfield": 1.0,    # Moxfield requires <= 1 req/sec
}

_locks: dict[str, threading.Lock] = {}
_last_call: dict[str, float] = {}
_global_lock = threading.Lock()


def wait(service: str, interval: float | None = None) -> None:
    """Block until it is safe to make the next request to *service*.

    Uses *interval* seconds between calls, falling back to
    ``DEFAULT_INTERVALS`` for known services, or 1.0s otherwise.
    """
    if interval is None:
        interval = DEFAULT_INTERVALS.get(service, 1.0)

    with _global_lock:
        if service not in _locks:
            _locks[service] = threading.Lock()
            _last_call[service] = 0.0
        lock = _locks[service]

    with lock:
        now = time.monotonic()
        elapsed = now - _last_call[service]
        if elapsed < interval:
            time.sleep(interval - elapsed)
        _last_call[service] = time.monotonic()


def reset(service: str | None = None) -> None:
    """Reset rate-limiter state. Mainly useful for tests."""
    with _global_lock:
        if service is None:
            _locks.clear()
            _last_call.clear()
        else:
            _locks.pop(service, None)
            _last_call.pop(service, None)
