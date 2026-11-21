"""Polite HTTP GET with retries, standard library only."""

from __future__ import annotations

import os
import ssl
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

USER_AGENT = "innovation-radar-harvester/0.1"
RETRY_STATUS = {429, 500, 502, 503, 504}
# Mozilla's root bundle as shipped with Git for Windows (used only when certifi is not installed)
WINDOWS_BUNDLES = (r"C:\Program Files\Git\mingw64\etc\ssl\certs\ca-bundle.crt",
                   r"C:\Program Files\Git\mingw64\ssl\certs\ca-bundle.crt")


def ssl_context() -> ssl.SSLContext:
    """Verified TLS with Mozilla's root set when available (the same roots Linux and our Docker image use).

    Python on Windows trusts the Windows stores, including cached intermediates. There new chains fail although
    the certificates are valid: Let's Encrypt "Root YE" via ISRG Root X2 ("certificate has expired": OpenSSL picks
    the cached X2 cross-signed by X1, which ended in 2025; ur.edu.pl, mielec.pl) and HARICA 2021 ("unable to get
    local issuer": bibliotekanauki.pl). So on Windows the context trusts the Windows ROOT store (not the cached
    intermediates of the CA store) plus a Mozilla bundle: RADAR_CA_BUNDLE (e.g. a corporate proxy CA), certifi, or
    Git for Windows' bundle. Elsewhere it is the system store, plus RADAR_CA_BUNDLE / certifi when present."""
    candidates = [os.environ.get("RADAR_CA_BUNDLE")]
    try:
        import certifi  # optional

        candidates.append(certifi.where())
    except ImportError:
        pass
    if sys.platform == "win32":
        candidates.extend(WINDOWS_BUNDLES)
    bundle = next((c for c in candidates if c and Path(c).is_file()), None)
    if sys.platform != "win32":
        ctx = ssl.create_default_context()
        if bundle:
            ctx.load_verify_locations(cafile=bundle)
        return ctx
    ctx = ssl.create_default_context(cafile=bundle) if bundle else ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    for cert, encoding, trust in ssl.enum_certificates("ROOT"):
        if encoding == "x509_asn" and (trust is True or ssl.Purpose.SERVER_AUTH.oid in trust):
            try:
                ctx.load_verify_locations(cadata=cert)
            except ssl.SSLError:
                continue
    return ctx


# every urlopen() in the harvester (connectors, crawler, robots.txt) goes through this opener
urllib.request.install_opener(urllib.request.build_opener(urllib.request.HTTPSHandler(context=ssl_context())))


def ascii_url(url: str) -> str:
    """IRI -> URI: http.client sends ASCII only, so 'https://www.dolinalotnicza.pl/członkowie' is percent-encoded
    (and an international host IDNA-encoded); an already encoded URL is left as it is."""
    if url.isascii():
        return url
    parts = urlsplit(url)
    host = parts.hostname or ""
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError:
        pass
    netloc = host + (f":{parts.port}" if parts.port else "")
    if parts.username:
        netloc = parts.username + (f":{parts.password}" if parts.password else "") + "@" + netloc
    safe = "/%:@!$&'()*+,;=-._~"
    return urlunsplit((parts.scheme, netloc, quote(parts.path, safe=safe), quote(parts.query, safe=safe + "?"),
                       quote(parts.fragment, safe=safe)))


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
        req = urllib.request.Request(ascii_url(url), headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
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
            ascii_url(url),
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
