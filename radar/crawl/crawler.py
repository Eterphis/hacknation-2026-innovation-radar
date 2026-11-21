"""One pass over a configured site: queue -> polite fetch -> extract -> classify -> record in the store.

Page states in `crawl_pages.status`:
  queued      discovered, never fetched
  list        start page or a `follow` page: only a source of links, revisited every `interval_hours`
  record      kept as a record (`record_id`), revisited every `revisit_days`
  skipped     fetched but not kept (reason), revisited every 2 x `revisit_days`
  robots      disallowed by robots.txt, retried after 30 days
  blocked     anti-bot protection answered (never worked around)
  error       network/HTTP error, retried after a day
  gone        404/410 once, retried after a day
  gone_final  404/410 twice: its record (if any) is marked removed and the page is not visited again
"""
from __future__ import annotations

import gzip
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from .. import store
from .classify import classify
from .extract import best_title, extract_html, extract_pdf, published_date
from .fetcher import Fetcher, FetchResult
from .frontier import canonical_url, due_pages, enqueue, in_scope, later, now_iso, parse_sitemap, update_page
from .normalize import build_record
from .sites import Site

RAW_ROOT = Path("data/raw/web")
MAX_SITEMAP_FILES = 5
MAX_SITEMAP_URLS = 2000
ROBOTS_RETRY_H = 30 * 24
ERROR_RETRY_H = 24
BLOCKED_RETRY_H = 7 * 24
GONE_LIMIT = 2


def _new_stats(site: Site) -> dict:
    return {"site": site.id, "source": site.source, "category": site.category, "status": "ok", "error": None,
            "fetched": 0, "added": 0, "changed": 0, "unchanged": 0, "not_modified": 0, "skipped": 0,
            "lists": 0, "gone": 0, "removed": 0, "errors": 0, "blocked": 0, "robots": 0, "queued": 0,
            "decisions": []}


def _path_query(url: str) -> str:
    p = urlsplit(url)
    return p.path + ("?" + p.query if p.query else "")


def _is_list(site: Site, row: sqlite3.Row) -> bool:
    return row["depth"] == 0 or site.is_follow(_path_query(row["url"]))


def _hours_for(site: Site, status: str) -> float:
    if status == "list":
        return site.interval_hours
    if status == "skipped":
        return 2 * site.revisit_days * 24
    return site.revisit_days * 24


def _save_site(conn: sqlite3.Connection, site: Site, **fields) -> None:
    conn.execute("INSERT INTO crawl_sites(site_id, category, config) VALUES (?,?,?) "
                 "ON CONFLICT(site_id) DO UPDATE SET category=excluded.category, config=excluded.config",
                 (site.id, site.category, json.dumps(site.to_json(), ensure_ascii=False)))
    if fields:
        sets = ", ".join(f"{k}=?" for k in fields)
        conn.execute(f"UPDATE crawl_sites SET {sets} WHERE site_id=?", (*fields.values(), site.id))


def _hours_since(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        then = datetime.fromisoformat(iso)
    except ValueError:
        return None
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - then).total_seconds() / 3600


def discover_sitemaps(conn: sqlite3.Connection, site: Site, fetcher: Fetcher) -> int:
    """Queue in-scope URLs from the sitemaps named in robots.txt and /sitemap.xml (depth 1)."""
    todo: list[str] = []
    for start in site.start:
        parts = urlsplit(start)
        for sm in fetcher.sitemaps(start) + [f"{parts.scheme}://{parts.netloc}/sitemap.xml"]:
            sm = canonical_url(sm)
            if sm and sm not in todo:
                todo.append(sm)
    seen: set[str] = set()
    added = files = 0
    while todo and files < MAX_SITEMAP_FILES and added < MAX_SITEMAP_URLS:
        sm = todo.pop(0)
        if sm in seen:
            continue
        seen.add(sm)
        res = fetcher.get(sm)
        files += 1
        if res.status != "ok":
            continue
        content = res.content
        if content[:2] == b"\x1f\x8b":
            try:
                content = gzip.decompress(content)
            except OSError:
                continue
        urls, nested = parse_sitemap(content.decode("utf-8", errors="replace"), sm)
        todo += [n for n in nested if n not in seen]
        for url, _lastmod in urls:
            if added >= MAX_SITEMAP_URLS:
                break
            if in_scope(site, url) and enqueue(conn, site, url, 1):
                added += 1
    conn.commit()
    return added


def _save_raw(raw_root: Path, site: Site, res: FetchResult) -> str:
    digest = hashlib.sha256(res.content).hexdigest()[:16]
    ext = "pdf" if res.kind == "pdf" else "html"
    path = Path(raw_root) / site.id / f"{digest}.{ext}.gz"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(gzip.compress(res.content))
        tmp.replace(path)
    return path.as_posix()


def _process(conn: sqlite3.Connection, site: Site, fetcher: Fetcher, row: sqlite3.Row, stats: dict,
             raw_root: Path, dry_run: bool) -> bool:
    """Fetch and handle one page. Returns False when the whole site must stop (start page blocked)."""
    url, depth = row["url"], row["depth"]
    res = fetcher.get(url, etag=row["etag"], last_modified=row["last_modified"])
    stats["fetched"] += 1
    base = {"http_status": res.http_status, "fetched_at": res.fetched_at}

    if res.status == "robots":
        stats["robots"] += 1
        update_page(conn, url, status="robots", reason=res.error, next_due=later(ROBOTS_RETRY_H), **base)
        return True
    if res.status == "blocked":
        stats["blocked"] += 1
        update_page(conn, url, status="blocked", reason=res.error, next_due=later(BLOCKED_RETRY_H), **base)
        if depth == 0:
            stats["status"], stats["error"] = "blocked", f"{url}: {res.error}"
            return False
        return True
    if res.status == "error":
        stats["errors"] += 1
        update_page(conn, url, status="error", reason=res.error, next_due=later(ERROR_RETRY_H), **base)
        return True
    if res.status == "gone":
        misses = row["misses"] + 1
        if misses >= GONE_LIMIT:
            update_page(conn, url, status="gone_final", misses=misses, reason=res.error, next_due=None, **base)
            if row["record_id"] and not dry_run:
                stats["removed"] += store.mark_removed(conn, site.source, [row["record_id"]])
        else:
            update_page(conn, url, status="gone", misses=misses, reason=res.error, next_due=later(ERROR_RETRY_H), **base)
        stats["gone"] += 1
        return True

    is_list = _is_list(site, row)
    prev = row["status"]
    if res.status == "not_modified":
        stats["not_modified"] += 1
        status = prev if prev in ("list", "record", "skipped") else ("list" if is_list else "skipped")
        update_page(conn, url, status=status, misses=0, next_due=later(_hours_for(site, status)), **base)
        return True

    # ok
    page = None
    if res.kind == "html":
        page = extract_html(res.text(), url)
    elif res.kind == "pdf":
        page = extract_pdf(res.content, url)
        if page is None:
            reason = "PDF bez tekstu (brak pakietu pypdf)"
            stats["skipped"] += 1
            update_page(conn, url, status="skipped", reason=reason, misses=0, content_type=res.content_type,
                        etag=res.etag, last_modified=res.last_modified, next_due=later(_hours_for(site, "skipped")), **base)
            return True
    if page is None:
        stats["skipped"] += 1
        update_page(conn, url, status="skipped", reason=f"nieobsługiwany typ treści ({res.content_type or res.kind})",
                    misses=0, content_type=res.content_type, next_due=later(_hours_for(site, "skipped")), **base)
        return True

    if res.kind == "html" and depth < site.max_depth:
        for href, _text in page.links:
            link = canonical_url(href, res.url)
            if link and link != url and in_scope(site, link) and enqueue(conn, site, link, depth + 1):
                stats["queued"] += 1

    common = dict(misses=0, content_type=res.content_type, etag=res.etag, last_modified=res.last_modified, **base)
    if is_list:
        stats["lists"] += 1
        update_page(conn, url, status="list", reason="lista / strona startowa", next_due=later(site.interval_hours), **common)
        return True

    content_hash = hashlib.sha256(page.text.encode("utf-8")).hexdigest()
    if content_hash == row["content_hash"] and prev in ("record", "skipped"):
        stats["unchanged"] += 1
        update_page(conn, url, status=prev, next_due=later(_hours_for(site, prev)), **common)
        return True

    title = best_title(page, site.name)
    published = published_date(page)
    sig = classify(title, page.body_text, published=published, keep_all=site.keep_all, min_score=site.min_score,
                   noindex=page.noindex, kind=page.kind)
    if sig.keep and site.require_date and not published:
        sig.keep, sig.reason = False, "brak daty publikacji (witryna z require_date)"
    decision = {"url": url, "keep": sig.keep, "reason": sig.reason, "title": title, "page_type": sig.page_type,
                "published": published, "score": round(sig.score, 2)}
    if not sig.keep:
        stats["skipped"] += 1
        stats["decisions"].append(decision)
        update_page(conn, url, status="skipped", reason=sig.reason, content_hash=content_hash,
                    next_due=later(_hours_for(site, "skipped")), **common)
        return True

    raw_file = None if dry_run else _save_raw(raw_root, site, res)
    rec = build_record(site, page, sig, fetched_at=res.fetched_at, etag=res.etag, last_modified=res.last_modified,
                       raw_file=raw_file)
    decision["organizations"] = [o["name"] for o in rec["organizations"]]
    stats["decisions"].append(decision)
    counts = store.upsert_source(conn, site.source, [rec], mark_removed=False, category=site.category)
    for k in ("added", "changed", "unchanged"):
        stats[k] += counts[k]
    update_page(conn, url, status="record", record_id=rec["record_id"], reason=sig.reason, content_hash=content_hash,
                next_due=later(_hours_for(site, "record")), **common)
    return True


def crawl_site(conn: sqlite3.Connection, site: Site, fetcher: Fetcher | None = None, *, max_pages: int | None = None,
               raw_root: Path = RAW_ROOT, dry_run: bool = False, now: str | None = None) -> dict:
    """Visit the pages of `site` that are due, within the page budget. Commits after every page."""
    stats = _new_stats(site)
    fetcher = fetcher or Fetcher(delay=site.delay)
    old_delay = fetcher.delay
    fetcher.delay = max(fetcher.delay, site.delay)
    row = conn.execute("SELECT last_run FROM crawl_sites WHERE site_id=?", (site.id,)).fetchone()
    last_run = row["last_run"] if row else None
    _save_site(conn, site, status="running", error=None)
    try:
        for start in site.start:
            url = canonical_url(start)
            if url:
                enqueue(conn, site, url, 0)
        conn.commit()
        since = _hours_since(last_run)
        if site.use_sitemap and (since is None or since >= site.revisit_days * 24):
            stats["queued"] += discover_sitemaps(conn, site, fetcher)

        budget = max_pages if max_pages is not None else site.max_pages
        running = True
        while running and stats["fetched"] < budget:
            rows = due_pages(conn, site, budget - stats["fetched"], now)
            if not rows:
                break
            for page_row in rows:
                running = _process(conn, site, fetcher, page_row, stats, raw_root, dry_run)
                conn.commit()
                if not running:
                    break
        if stats["status"] == "ok" and stats["fetched"] and stats["errors"] == stats["fetched"]:
            stats["status"], stats["error"] = "error", "wszystkie zapytania zakończone błędem"
    except Exception as e:  # keep the site's state honest, then let the caller decide
        stats["status"], stats["error"] = "error", f"{type(e).__name__}: {e}"
        _save_site(conn, site, last_run=now_iso(), status="error", error=stats["error"])
        conn.commit()
        raise
    finally:
        fetcher.delay = old_delay
    _save_site(conn, site, last_run=now_iso(), status=stats["status"], error=stats["error"])
    conn.commit()
    return stats


def site_is_due(conn: sqlite3.Connection, site: Site, now: str | None = None) -> bool:
    row = conn.execute("SELECT last_run FROM crawl_sites WHERE site_id=?", (site.id,)).fetchone()
    since = _hours_since(row["last_run"] if row else None)
    if since is None or since >= site.interval_hours:
        return True
    return bool(due_pages(conn, site, 1, now))


def crawl_due(conn: sqlite3.Connection, sites: list[Site], fetcher: Fetcher | None = None, *,
              max_pages: int | None = None, raw_root: Path = RAW_ROOT, dry_run: bool = False,
              force: bool = False) -> list[dict]:
    """Run every enabled site whose interval has passed or which has pages due (all of them with force)."""
    fetcher = fetcher or Fetcher()
    out = []
    for site in sites:
        if not site.enabled:
            continue
        if not force and not site_is_due(conn, site):
            continue
        try:
            out.append(crawl_site(conn, site, fetcher, max_pages=max_pages, raw_root=raw_root, dry_run=dry_run))
        except Exception as e:
            stats = _new_stats(site)
            stats["status"], stats["error"] = "error", f"{type(e).__name__}: {e}"
            out.append(stats)
    return out


def totals(results: list[dict]) -> dict:
    keys = ("fetched", "added", "changed", "unchanged", "not_modified", "skipped", "lists", "gone", "removed",
            "errors", "blocked", "robots", "queued")
    t = {k: sum(r.get(k, 0) for r in results) for k in keys}
    t["sites"] = len(results)
    t["blocked_sites"] = [r["site"] for r in results if r["status"] == "blocked"]
    t["failed_sites"] = [r["site"] for r in results if r["status"] == "error"]
    return t
