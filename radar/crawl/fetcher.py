"""Polite HTTP for the crawler: robots.txt, a delay per host, conditional GET, size limit, and
recognising bot challenges (which are reported as `blocked`, never worked around)."""
from __future__ import annotations

import socket
import time
import urllib.error
import urllib.request
import urllib.robotparser
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable
from urllib.parse import urlsplit

from ..http import USER_AGENT

MAX_BYTES = 15 * 1024 * 1024
CHALLENGE_MARKERS = ("incapsula", "_incapsula_resource", "cf-chl", "cf_chl", "challenge-platform",
                     "verifying browser", "verify you are human", "captcha", "high load")


@dataclass
class FetchResult:
    url: str                       # final URL after redirects
    status: str                    # ok | not_modified | gone | blocked | robots | error
    http_status: int | None = None
    content: bytes = b""
    content_type: str = ""
    etag: str | None = None
    last_modified: str | None = None
    fetched_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    error: str | None = None

    @property
    def kind(self) -> str:
        ct = self.content_type.lower()
        if "pdf" in ct or self.content[:5] == b"%PDF-":
            return "pdf"
        if "xml" in ct and "html" not in ct:
            return "xml"
        if "html" in ct or self.content.lstrip()[:15].lower().startswith((b"<!doctype html", b"<html")):
            return "html"
        return "other"

    def text(self) -> str:
        charset = "utf-8"
        for part in self.content_type.split(";"):
            part = part.strip().lower()
            if part.startswith("charset="):
                charset = part.split("=", 1)[1].strip('"') or "utf-8"
        try:
            return self.content.decode(charset, errors="replace")
        except LookupError:
            return self.content.decode("utf-8", errors="replace")


def looks_like_challenge(status: int | None, body: bytes) -> bool:
    if status not in (200, 202, 403, 429, 503):
        return False
    head = body[:20000].decode("utf-8", errors="ignore").lower()
    if status == 200 and len(head) > 5000 and "<article" in head:
        return False  # a real page that merely mentions "captcha" in a form
    return any(m in head for m in CHALLENGE_MARKERS)


Opener = Callable[[urllib.request.Request, float], object]


def _default_open(req: urllib.request.Request, timeout: float):
    return urllib.request.urlopen(req, timeout=timeout)


class Fetcher:
    def __init__(self, delay: float = 2.0, timeout: float = 30.0, opener: Opener | None = None,
                 sleep: Callable[[float], None] = time.sleep, respect_robots: bool = True) -> None:
        self.delay = delay
        self.timeout = timeout
        self.open = opener or _default_open
        self.sleep = sleep
        self.respect_robots = respect_robots
        self._last: dict[str, float] = {}
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}

    # --- politeness ------------------------------------------------------------
    def _wait(self, host: str, delay: float | None = None) -> None:
        delay = self.delay if delay is None else delay
        last = self._last.get(host)
        if last is not None:
            gap = time.monotonic() - last
            if gap < delay:
                self.sleep(delay - gap)
        self._last[host] = time.monotonic()

    def robots(self, url: str) -> urllib.robotparser.RobotFileParser | None:
        parts = urlsplit(url)
        base = f"{parts.scheme}://{parts.netloc}"
        if base not in self._robots:
            rp = urllib.robotparser.RobotFileParser(base + "/robots.txt")
            res = self._get(base + "/robots.txt", check_robots=False)
            if res.status == "ok":
                rp.parse(res.text().splitlines())
            elif res.http_status in (401, 403):
                rp.disallow_all = True  # robots.txt itself forbidden: treat the site as closed
            else:
                rp.allow_all = True     # no robots.txt: everything allowed
            self._robots[base] = rp
        return self._robots[base]

    def allowed(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        rp = self.robots(url)
        return rp is None or rp.can_fetch(USER_AGENT, url)

    def crawl_delay(self, url: str) -> float | None:
        rp = self.robots(url) if self.respect_robots else None
        d = rp.crawl_delay(USER_AGENT) if rp else None
        return float(d) if d else None

    def sitemaps(self, url: str) -> list[str]:
        rp = self.robots(url) if self.respect_robots else None
        return list((rp.site_maps() if rp else None) or [])

    # --- requests --------------------------------------------------------------
    def get(self, url: str, etag: str | None = None, last_modified: str | None = None) -> FetchResult:
        if not self.allowed(url):
            return FetchResult(url, "robots", error="zablokowane przez robots.txt")
        return self._get(url, etag=etag, last_modified=last_modified)

    def _get(self, url: str, etag: str | None = None, last_modified: str | None = None,
             check_robots: bool = True) -> FetchResult:
        host = urlsplit(url).netloc
        delay = max(self.delay, self.crawl_delay(url) or 0) if check_robots else self.delay
        self._wait(host, delay)
        headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,application/xml,application/pdf;q=0.9,*/*;q=0.5",
                   "Accept-Language": "pl,en;q=0.5"}
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified
        req = urllib.request.Request(url, headers=headers)
        try:
            resp = self.open(req, self.timeout)
            with resp:
                body = resp.read(MAX_BYTES + 1)
                status = getattr(resp, "status", 200)
                info = resp.headers
                final = resp.geturl() if hasattr(resp, "geturl") else url
        except urllib.error.HTTPError as e:
            body = e.read(20000) if hasattr(e, "read") else b""
            if e.code == 304:
                return FetchResult(url, "not_modified", 304, etag=etag, last_modified=last_modified)
            if e.code in (404, 410):
                return FetchResult(url, "gone", e.code, error=f"HTTP {e.code}")
            if looks_like_challenge(e.code, body):
                return FetchResult(url, "blocked", e.code, error="ochrona antybotowa (nie obchodzimy)")
            return FetchResult(url, "error", e.code, error=f"HTTP {e.code}")
        except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, OSError) as e:
            return FetchResult(url, "error", None, error=f"{type(e).__name__}: {e}")
        if len(body) > MAX_BYTES:
            return FetchResult(final, "error", status, error=f"plik większy niż {MAX_BYTES // 1024 // 1024} MB")
        if looks_like_challenge(status, body):
            return FetchResult(final, "blocked", status, error="ochrona antybotowa (nie obchodzimy)")
        return FetchResult(final, "ok", status, body, info.get("Content-Type", "") or "",
                           info.get("ETag"), info.get("Last-Modified"))
