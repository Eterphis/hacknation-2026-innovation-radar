"""Shared HTTP client with retry and backoff (Release It!: timeouts on every call, bounded retries)."""

import time

import httpx

from radar.config import get_settings

RETRY_STATUS = {429, 500, 502, 503, 504}


def client(headers: dict | None = None, timeout: float | None = None) -> httpx.Client:
    """Headers whose value is empty after ${ENV} expansion are dropped (e.g. "Bearer " without a token)."""
    s = get_settings()
    h = {"User-Agent": s.http_user_agent}
    h.update({k: v for k, v in (headers or {}).items() if v and str(v).strip() not in ("", "Bearer")})
    return httpx.Client(timeout=timeout or s.http_timeout_s, headers=h, follow_redirects=True)


def request(c: httpx.Client, method: str, url: str, *, attempts: int = 4, **kw) -> httpx.Response:
    delay = 1.0
    for i in range(attempts):
        try:
            r = c.request(method, url, **kw)
            if r.status_code not in RETRY_STATUS:
                r.raise_for_status()
                return r
            if i == attempts - 1:
                r.raise_for_status()
            retry_after = r.headers.get("Retry-After")
            wait = float(retry_after) if retry_after and retry_after.isdigit() else delay
        except httpx.TransportError:
            if i == attempts - 1:
                raise
            wait = delay
        time.sleep(min(wait, 60))
        delay *= 2
    raise RuntimeError("unreachable")
