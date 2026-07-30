"""Small retry/backoff helper for the network-facing clients.

Only *transient* failures are retried — connection errors, timeouts, and 429/5xx
gateway statuses. Permanent failures (4xx like the 422 validation / 500-IO-limit
errors) are raised immediately, so a bad request fails fast instead of hammering the
API. `sleep` is injectable so the backoff is unit-tested without real waiting.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Optional

# Gateway statuses worth retrying (rate limit + transient server/proxy errors).
TRANSIENT_STATUS = {429, 500, 502, 503, 504}


class TransientAPIError(Exception):
    """A retryable API response (transient status in the payload)."""

    def __init__(self, status: Any = None, message: Any = None):
        self.status = status
        super().__init__(f"transient API error {status}: {message}")


def is_transient_status(code: Any) -> bool:
    try:
        return int(code) in TRANSIENT_STATUS
    except (TypeError, ValueError):
        return False


def is_transient_exception(exc: Exception) -> bool:
    """Generic transient check for HTTP-ish clients: a network error (requests
    ConnectionError/Timeout) or an exception carrying a transient HTTP status
    (`.status` or `.status_code`), e.g. simple-salesforce's SalesforceError."""
    try:
        import requests
        if isinstance(exc, requests.exceptions.RequestException):
            return True
    except ImportError:  # pragma: no cover
        pass
    if isinstance(exc, TransientAPIError):
        return True
    for attr in ("status", "status_code"):
        if is_transient_status(getattr(exc, attr, None)):
            return True
    return False


def with_retries(fn: Callable[[], Any], *, attempts: int = 4, base_delay: float = 2.0,
                 max_delay: float = 30.0,
                 retry_on: Callable[[Exception], bool] = lambda e: True,
                 sleep: Callable[[float], None] = time.sleep,
                 on_retry: Optional[Callable[[int, Exception, float], None]] = None) -> Any:
    """Call `fn`, retrying up to `attempts` times with exponential backoff
    (`base_delay * 2**i`, capped at `max_delay`) while `retry_on(exc)` is true."""
    last: Optional[Exception] = None
    for i in range(max(1, attempts)):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 — re-raised below if not retryable
            last = exc
            if i == attempts - 1 or not retry_on(exc):
                raise
            delay = min(max_delay, base_delay * (2 ** i))
            if on_retry:
                on_retry(i + 1, exc, delay)
            sleep(delay)
    assert last is not None
    raise last
