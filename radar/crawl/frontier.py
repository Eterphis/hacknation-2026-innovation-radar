"""Canonical URLs, crawl scope, sitemaps and the page queue kept in the database (crawl_pages)."""
from __future__ import annotations

import re
import sqlite3
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

from .sites import Site

TRACKING = re.compile(r"^(utm_\w+|fbclid|gclid|mc_cid|mc_eid|_ga|yclid|ref|share|print|replytocom)$", re.I)
SKIP_EXT = re.compile(r"\.(jpe?g|png|gif|svg|webp|ico|bmp|tiff?|css|js|mjs|json|zip|rar|7z|gz|tar|mp[34]|avi|mov|wmv|"
                      r"webm|ogg|wav|docx?|xlsx?|pptx?|odt|ods|odp|rtf|exe|msi|dmg|apk|ics|vcf|woff2?|ttf|eot)$", re.I)
SKIP_PATH = re.compile(r"/(wp-admin|wp-login|wp-json|feed|xmlrpc|login|logowanie|rejestracja|koszyk|cart|search|szukaj)"
                       r"(/|$|\?)|[?&](s|q|search|page_id|lang|replytocom)=", re.I)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def later(hours: float, base: datetime | None = None) -> str:
    return ((base or datetime.now(timezone.utc)) + timedelta(hours=hours)).isoformat(timespec="seconds")


def canonical_url(url: str, base: str | None = None) -> str | None:
    """Absolute http(s) URL without fragment, tracking parameters, default port or empty query."""
    if base:
        url = urljoin(base, url.strip())
    url = url.strip()
    parts = urlsplit(url)
    if parts.scheme.lower() not in ("http", "https") or not parts.netloc:
        return None
    host = parts.hostname.lower() if parts.hostname else ""
    port = parts.port
    netloc = host if port in (None, 80, 443) else f"{host}:{port}"
    query = urlencode(sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not TRACKING.match(k)))
    path = re.sub(r"/{2,}", "/", parts.path or "/")
    return urlunsplit((parts.scheme.lower(), netloc, path, query, ""))


def _host_key(host: str) -> str:
    return host[4:] if host.startswith("www.") else host


def in_scope(site: Site, url: str) -> bool:
    parts = urlsplit(url)
    hosts = {_host_key(urlsplit(s).hostname or "") for s in site.start}
    if _host_key(parts.hostname or "") not in hosts:
        return False
    pq = parts.path + ("?" + parts.query if parts.query else "")
    if SKIP_EXT.search(parts.path) or SKIP_PATH.search(pq):
        return False
    return site.matches(pq)


def parse_sitemap(xml_text: str, base: str) -> tuple[list[tuple[str, str | None]], list[str]]:
    """-> ([(url, lastmod)], [nested sitemap urls]). Tolerates namespaces and junk."""
    try:
        root = ET.fromstring(xml_text.encode("utf-8") if isinstance(xml_text, str) else xml_text)
    except ET.ParseError:
        return [], []
    urls, nested = [], []
    for el in root.iter():
        tag = el.tag.rsplit("}", 1)[-1]
        if tag not in ("url", "sitemap"):
            continue
        loc = lastmod = None
        for child in el:
            ctag = child.tag.rsplit("}", 1)[-1]
            if ctag == "loc" and child.text:
                loc = canonical_url(child.text, base)
            elif ctag == "lastmod" and child.text:
                lastmod = child.text.strip()
        if loc:
            (nested.append(loc) if tag == "sitemap" else urls.append((loc, lastmod)))
    return urls, nested


# --- queue in the database -----------------------------------------------------
def enqueue(conn: sqlite3.Connection, site: Site, url: str, depth: int, due: str | None = None) -> bool:
    cur = conn.execute("INSERT OR IGNORE INTO crawl_pages(url, site_id, depth, status, discovered_at, next_due) "
                       "VALUES (?,?,?,?,?,?)", (url, site.id, depth, "queued", now_iso(), due or now_iso()))
    if cur.rowcount == 0 and depth == 0:
        # a start page that already exists keeps depth 0 (it may have been found deeper first)
        conn.execute("UPDATE crawl_pages SET depth=0 WHERE url=? AND depth>0", (url,))
    return cur.rowcount > 0


def due_pages(conn: sqlite3.Connection, site: Site, limit: int, now: str | None = None) -> list[sqlite3.Row]:
    now = now or now_iso()
    return conn.execute(
        "SELECT * FROM crawl_pages WHERE site_id=? AND status NOT IN ('gone_final') AND (next_due IS NULL OR next_due<=?) "
        "ORDER BY (status='queued') DESC, depth, discovered_at LIMIT ?", (site.id, now, limit)).fetchall()


def update_page(conn: sqlite3.Connection, url: str, **fields) -> None:
    sets = ", ".join(f"{k}=?" for k in fields)
    conn.execute(f"UPDATE crawl_pages SET {sets} WHERE url=?", (*fields.values(), url))
