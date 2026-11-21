"""Polite HTTP GET with retries, standard library only."""

from __future__ import annotations

import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone

USER_AGENT = "innovation-radar-harvester/0.1"
RETRY_STATUS = {429, 500, 502, 503, 504}


class FetchError(Exception):
    pass


@dataclass
class Response:
    url: str
    status: int
    text: str
    fetched_at: str


@dataclass
class BinaryResponse:
    url: str
    status: int
    content: bytes
    content_type: str
    fetched_at: str


def fetch_bytes(url: str, timeout: float = 60.0, retries: int = 3, backoff: float = 2.0) -> BinaryResponse:
    """Like fetch(), but returns raw bytes (spreadsheets, PDFs)."""
    last: Exception | None = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return BinaryResponse(
                    url=resp.geturl(), status=resp.status, content=resp.read(),
                    content_type=resp.headers.get("Content-Type", ""),
                    fetched_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                )
        except urllib.error.HTTPError as e:
            last = e
            if e.code not in RETRY_STATUS:
                raise FetchError(f"HTTP {e.code} for {url}") from e
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last = e
        if attempt < retries:
            time.sleep(backoff * (2**attempt))
    raise FetchError(f"giving up on {url}: {last}") from last


def fetch(url: str, timeout: float = 30.0, retries: int = 3, backoff: float = 2.0,
          accept: str = "text/html,application/xhtml+xml") -> Response:
    """GET `url`; retries timeouts, connection errors and 429/5xx with exponential backoff."""
    last: Exception | None = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": accept,
                "Accept-Language": "pl,en;q=0.5",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                charset = resp.headers.get_content_charset() or "utf-8"
                body = resp.read().decode(charset, errors="replace")
                return Response(
                    url=resp.geturl(),
                    status=resp.status,
                    text=body,
                    fetched_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                )
        except urllib.error.HTTPError as e:
            last = e
            if e.code not in RETRY_STATUS:
                raise FetchError(f"HTTP {e.code} for {url}") from e
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last = e
        if attempt < retries:
            time.sleep(backoff * (2**attempt))
    raise FetchError(f"giving up on {url}: {last}") from last
