"""Small in-memory rate limiter (one server process). Stops password guessing and sign-up spam."""
import threading
import time
from collections import deque

from fastapi import HTTPException, Request

_lock = threading.Lock()
_hits: dict[str, deque] = {}


def client_ip(request: Request) -> str:
    # uvicorn runs with --proxy-headers, so this is the visitor's address, not Render's proxy.
    return request.client.host if request.client else "unknown"


def check(key: str, limit: int, window: int) -> None:
    """Raise 429 if `key` already has `limit` recorded hits inside the last `window` seconds."""
    now = time.monotonic()
    with _lock:
        if len(_hits) > 5000:
            for k in [k for k, d in _hits.items() if not d or now - d[-1] > 86400]:
                del _hits[k]
        dq = _hits.get(key)
        if not dq:
            return
        while dq and now - dq[0] > window:
            dq.popleft()
        if len(dq) >= limit:
            wait = int(window - (now - dq[0])) + 1
            minutes = max(1, (wait + 59) // 60)
            raise HTTPException(429, f"Too many attempts. Please try again in {minutes} minute{'s' if minutes != 1 else ''}.",
                                headers={"Retry-After": str(wait)})


def hit(key: str) -> None:
    with _lock:
        _hits.setdefault(key, deque()).append(time.monotonic())


def clear(key: str) -> None:
    with _lock:
        _hits.pop(key, None)
