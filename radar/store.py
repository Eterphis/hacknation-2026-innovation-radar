"""Baza danych radaru (SQLite, biblioteka standardowa): rekordy z historią zmian, wyszukiwanie
pełnotekstowe, organizacje, karty i przebiegi odświeżania.

    python -X utf8 -m radar.store init
    python -X utf8 -m radar.store import data/normalized/ncbr.jsonl data/normalized/interreg.jsonl
    python -X utf8 -m radar.store stats
    python -X utf8 -m radar.store search swiatlowod
    python -X utf8 -m radar.store export --source ncbr_sukcesy --out ncbr.jsonl

Rekord jest identyfikowany parą (source, record_id). Zmiana `content_hash` zapisuje nową wersję,
rekord, którego zabrakło w nowym pobraniu źródła, dostaje `removed_at` (nie jest kasowany).
Ścieżka bazy: opcja `--db` albo zmienna `RADAR_DB` (domyślnie data/radar.db).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .text import fold

DEFAULT_DB = "data/radar.db"
LEADING_ROLES = ("beneficiary", "lead_partner")


def default_db() -> str:
    return os.environ.get("RADAR_DB") or DEFAULT_DB


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


MIGRATIONS = [
    # v1
    """
    CREATE TABLE records (
        source TEXT NOT NULL,
        record_id TEXT NOT NULL,
        source_name TEXT,
        title TEXT,
        content_hash TEXT,
        quality TEXT,
        voivodeships TEXT,          -- JSON list
        total_value REAL,
        currency TEXT,
        period_start TEXT,
        period_end TEXT,
        first_seen TEXT NOT NULL,
        last_seen TEXT NOT NULL,
        changed_at TEXT NOT NULL,
        removed_at TEXT,
        data TEXT NOT NULL,         -- full radar.record/v1 JSON
        PRIMARY KEY (source, record_id)
    );
    CREATE INDEX records_quality ON records(quality);
    CREATE TABLE record_versions (
        source TEXT NOT NULL,
        record_id TEXT NOT NULL,
        content_hash TEXT NOT NULL,
        seen_at TEXT NOT NULL,
        data TEXT NOT NULL,
        PRIMARY KEY (source, record_id, seen_at),
        FOREIGN KEY (source, record_id) REFERENCES records(source, record_id) ON DELETE CASCADE
    );
    CREATE TABLE organizations (
        org_id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        name_key TEXT NOT NULL UNIQUE,
        nip TEXT,
        type TEXT
    );
    CREATE TABLE record_orgs (
        source TEXT NOT NULL,
        record_id TEXT NOT NULL,
        org_id INTEGER NOT NULL REFERENCES organizations(org_id),
        role TEXT,
        PRIMARY KEY (source, record_id, org_id, role),
        FOREIGN KEY (source, record_id) REFERENCES records(source, record_id) ON DELETE CASCADE
    );
    CREATE TABLE cards (
        card_id TEXT PRIMARY KEY,
        source TEXT,
        record_id TEXT,
        record_content_hash TEXT,
        status TEXT,
        total REAL,
        light TEXT,
        created_at TEXT NOT NULL,
        data TEXT NOT NULL
    );
    CREATE INDEX cards_record ON cards(source, record_id);
    CREATE TABLE refresh_runs (
        id INTEGER PRIMARY KEY,
        source TEXT NOT NULL,
        at TEXT NOT NULL,
        ok INTEGER NOT NULL,
        download TEXT,
        rebuild TEXT,
        records INTEGER,
        added INTEGER,
        changed INTEGER,
        removed INTEGER,
        error TEXT,
        warning TEXT,
        seconds REAL,
        input_sha256 TEXT,
        output_sha256 TEXT,
        details TEXT
    );
    CREATE INDEX refresh_runs_source ON refresh_runs(source, at);
    """,
    # v2: categories from the brief and the web crawler's state
    """
    ALTER TABLE records ADD COLUMN category TEXT;
    CREATE INDEX records_category ON records(category);
    CREATE TABLE crawl_sites (
        site_id TEXT PRIMARY KEY,
        category TEXT,
        config TEXT,
        last_run TEXT,
        status TEXT,
        error TEXT
    );
    CREATE TABLE crawl_pages (
        url TEXT PRIMARY KEY,
        site_id TEXT NOT NULL,
        depth INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'queued',   -- queued | record | skipped | gone | error | blocked
        http_status INTEGER,
        etag TEXT,
        last_modified TEXT,
        content_hash TEXT,
        content_type TEXT,
        discovered_at TEXT NOT NULL,
        fetched_at TEXT,
        next_due TEXT,
        record_id TEXT,
        reason TEXT,
        misses INTEGER NOT NULL DEFAULT 0
    );
    CREATE INDEX crawl_pages_due ON crawl_pages(site_id, next_due);
    """,
]

# share of a source's live records that may disappear in one harvest before we suspect a broken
# harvest (changed page layout, truncated file) instead of real removals
REMOVAL_GUARD_RATIO = 0.5

FTS_SQL = """CREATE VIRTUAL TABLE IF NOT EXISTS records_fts USING fts5(
    source UNINDEXED, record_id UNINDEXED, title, body, tokenize='unicode61 remove_diacritics 2')"""


def connect(path: str | Path | None = None) -> sqlite3.Connection:
    path = Path(path or default_db())
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    if str(path) != ":memory:":
        conn.execute("PRAGMA journal_mode=WAL")
    migrate(conn)
    return conn


def migrate(conn: sqlite3.Connection) -> None:
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    for i, script in enumerate(MIGRATIONS[version:], start=version + 1):
        with conn:
            conn.executescript(script)
            conn.execute(f"PRAGMA user_version={i}")
    try:
        conn.execute(FTS_SQL)
    except sqlite3.OperationalError:  # SQLite built without FTS5: search falls back to LIKE
        pass


def has_fts(conn: sqlite3.Connection) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE name='records_fts'").fetchone() is not None


# --- writing -------------------------------------------------------------------
def _search_body(rec: dict) -> str:
    parts = [rec.get("text_for_llm") or ""]
    parts += [o.get("name") or "" for o in rec.get("organizations") or []]
    parts += rec.get("keywords") or []
    return "\n".join(p for p in parts if p)


def _columns(rec: dict) -> dict:
    funding = rec.get("funding") or {}
    period = rec.get("period") or {}
    return {
        "source_name": rec.get("source_name"),
        "title": rec.get("title"),
        "content_hash": rec.get("content_hash"),
        "quality": (rec.get("quality") or {}).get("status"),
        "voivodeships": json.dumps((rec.get("region") or {}).get("voivodeships") or [], ensure_ascii=False),
        "total_value": funding.get("total_value"),
        "currency": funding.get("currency"),
        "period_start": period.get("start"),
        "period_end": period.get("end"),
        "data": json.dumps(rec, ensure_ascii=False),
    }


def _org_key(org: dict) -> str:
    nip = re.sub(r"\D", "", str(org.get("nip") or ""))
    return f"nip:{nip}" if len(nip) == 10 else "name:" + fold(org.get("name") or "")


def _link_orgs(conn: sqlite3.Connection, source: str, record_id: str, rec: dict) -> None:
    conn.execute("DELETE FROM record_orgs WHERE source=? AND record_id=?", (source, record_id))
    for org in rec.get("organizations") or []:
        if not org.get("name"):
            continue
        key = _org_key(org)
        conn.execute("INSERT INTO organizations(name, name_key, nip, type) VALUES (?,?,?,?) "
                     "ON CONFLICT(name_key) DO NOTHING",
                     (org["name"], key, org.get("nip"), org.get("type_hint")))
        org_id = conn.execute("SELECT org_id FROM organizations WHERE name_key=?", (key,)).fetchone()[0]
        conn.execute("INSERT OR IGNORE INTO record_orgs VALUES (?,?,?,?)", (source, record_id, org_id, org.get("role")))


def _index(conn: sqlite3.Connection, fts: bool, source: str, record_id: str, rec: dict) -> None:
    if not fts:
        return
    conn.execute("DELETE FROM records_fts WHERE source=? AND record_id=?", (source, record_id))
    conn.execute("INSERT INTO records_fts(source, record_id, title, body) VALUES (?,?,?,?)",
                 (source, record_id, fold(rec.get("title") or ""), fold(_search_body(rec))))


def upsert_source(conn: sqlite3.Connection, source: str, records: Iterable[dict],
                  seen_at: str | None = None, mark_removed: bool = True, category: str | None = None,
                  force_removal: bool = False) -> dict:
    """Write one harvest of a source. Returns counts added/changed/unchanged/restored/removed.

    mark_removed: the harvest is complete, so records missing from it left the source. When more than
    REMOVAL_GUARD_RATIO of the live records would go, nothing is marked (count in `removal_skipped`)
    unless force_removal: a broken harvest must not hide half the database."""
    seen_at = seen_at or now_iso()
    fts = has_fts(conn)
    counts = {"added": 0, "changed": 0, "unchanged": 0, "restored": 0, "removed": 0, "removal_skipped": 0}
    seen: set[str] = set()
    with conn:
        for rec in records:
            if rec.get("source") != source:
                raise ValueError(f"rekord {rec.get('record_id')} ma source={rec.get('source')!r}, oczekiwano {source!r}")
            rid = rec["record_id"]
            if rid in seen:
                continue
            seen.add(rid)
            cols = _columns(rec)
            if category:
                cols["category"] = category
            old = conn.execute("SELECT content_hash, removed_at FROM records WHERE source=? AND record_id=?",
                               (source, rid)).fetchone()
            if old is None:
                conn.execute(
                    "INSERT INTO records(source, record_id, first_seen, last_seen, changed_at, "
                    + ", ".join(cols) + ") VALUES (?,?,?,?,?," + ",".join("?" * len(cols)) + ")",
                    (source, rid, seen_at, seen_at, seen_at, *cols.values()))
                counts["added"] += 1
                changed = True
            else:
                changed = old["content_hash"] != cols["content_hash"]
                if old["removed_at"]:
                    counts["restored"] += 1
                counts["changed" if changed else "unchanged"] += 1
                sets = ", ".join(f"{k}=?" for k in cols) + ", last_seen=?, removed_at=NULL"
                vals = [*cols.values(), seen_at]
                if changed:
                    sets += ", changed_at=?"
                    vals.append(seen_at)
                conn.execute(f"UPDATE records SET {sets} WHERE source=? AND record_id=?", (*vals, source, rid))
            if changed:
                conn.execute("INSERT OR IGNORE INTO record_versions VALUES (?,?,?,?,?)",
                             (source, rid, cols["content_hash"] or "", seen_at, cols["data"]))
                _link_orgs(conn, source, rid, rec)
                _index(conn, fts, source, rid, rec)
        if mark_removed:
            live = conn.execute("SELECT record_id FROM records WHERE source=? AND removed_at IS NULL", (source,)).fetchall()
            gone = [r["record_id"] for r in live if r["record_id"] not in seen]
            if gone and len(gone) > REMOVAL_GUARD_RATIO * len(live) and not force_removal:
                counts["removal_skipped"] = len(gone)
                gone = []
            conn.executemany("UPDATE records SET removed_at=? WHERE source=? AND record_id=?",
                             [(seen_at, source, rid) for rid in gone])
            counts["removed"] = len(gone)
    return counts


def mark_removed(conn: sqlite3.Connection, source: str, record_ids: Iterable[str], at: str | None = None) -> int:
    """Mark single records as gone from the source (e.g. a crawled page answered 404 twice)."""
    at = at or now_iso()
    with conn:
        cur = conn.executemany("UPDATE records SET removed_at=? WHERE source=? AND record_id=? AND removed_at IS NULL",
                               [(at, source, rid) for rid in record_ids])
    return cur.rowcount


def read_jsonl(path: Path) -> list[dict]:
    with Path(path).open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def import_jsonl(conn: sqlite3.Connection, path: Path, seen_at: str | None = None) -> dict[str, dict]:
    """Import a connector's JSONL; records are grouped by source (one file normally holds one)."""
    by_source: dict[str, list[dict]] = {}
    for rec in read_jsonl(path):
        by_source.setdefault(rec["source"], []).append(rec)
    return {src: upsert_source(conn, src, recs, seen_at) for src, recs in by_source.items()}


def add_refresh_run(conn: sqlite3.Connection, source: str, res: dict) -> None:
    keys = ("at", "download", "rebuild", "records", "added", "changed", "removed", "error", "warning",
            "seconds", "input_sha256", "output_sha256")
    with conn:
        conn.execute(
            "INSERT INTO refresh_runs(source, ok, details, " + ", ".join(keys) + ") VALUES (?,?,?," + ",".join("?" * len(keys)) + ")",
            (source, 1 if res.get("ok") else 0, json.dumps(res, ensure_ascii=False), *(res.get(k) for k in keys)))


def last_successful_run(conn: sqlite3.Connection, source: str) -> dict:
    row = conn.execute("SELECT details FROM refresh_runs WHERE source=? AND ok=1 AND rebuild IN "
                       "('rebuilt', 'skipped_unchanged') ORDER BY id DESC LIMIT 1", (source,)).fetchone()
    return json.loads(row["details"]) if row else {}


def refresh_runs(conn: sqlite3.Connection, limit: int = 20) -> list[dict]:
    rows = conn.execute("SELECT * FROM refresh_runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [{k: r[k] for k in r.keys() if k != "details"} for r in rows]


def save_card(conn: sqlite3.Connection, card: dict, record: dict) -> None:
    scores = card.get("scores") or {}
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO cards VALUES (?,?,?,?,?,?,?,?,?)",
            (card["card_id"], record.get("source"), record.get("record_id"), record.get("content_hash"),
             card.get("status"), scores.get("total"), scores.get("light"), now_iso(), json.dumps(card, ensure_ascii=False)))


def stale_records(conn: sqlite3.Connection, quality: str | None = "ok") -> list[dict]:
    """Live records with no card or with a card made from another content_hash."""
    sql = ("SELECT r.data FROM records r WHERE r.removed_at IS NULL "
           + ("AND r.quality=? " if quality else "")
           + "AND NOT EXISTS (SELECT 1 FROM cards c WHERE c.source=r.source AND c.record_id=r.record_id "
             "AND c.record_content_hash IS r.content_hash) ORDER BY r.source, r.record_id")
    return [json.loads(r["data"]) for r in conn.execute(sql, (quality,) if quality else ())]


# --- reading -------------------------------------------------------------------
def _fts_query(q: str) -> str:
    words = re.findall(r"\w+", fold(q), re.UNICODE)
    return " ".join(f'"{w}"*' for w in words)


def list_records(conn: sqlite3.Connection, *, q: str | None = None, source: str | None = None,
                 category: str | None = None,
                 quality: str | None = None, voivodeship: str | None = None, include_removed: bool = False,
                 limit: int | None = None, offset: int = 0) -> list[dict]:
    where, params = [], []
    join = ""
    if q and q.strip():
        if has_fts(conn) and _fts_query(q):
            join = "JOIN records_fts f ON f.source=r.source AND f.record_id=r.record_id"
            where.append("records_fts MATCH ?")
            params.append(_fts_query(q))
        else:
            where.append("(r.title LIKE ? OR r.data LIKE ?)")
            params += [f"%{q}%", f"%{q}%"]
    for col, val in (("r.source", source), ("r.quality", quality), ("r.category", category)):
        if val:
            where.append(f"{col}=?")
            params.append(val)
    if voivodeship:
        where.append("EXISTS (SELECT 1 FROM json_each(r.voivodeships) WHERE value=?)")
        params.append(voivodeship)
    if not include_removed:
        where.append("r.removed_at IS NULL")
    sql = (f"SELECT r.* FROM records r {join} " + ("WHERE " + " AND ".join(where) if where else "")
           + (" ORDER BY bm25(records_fts)" if join else " ORDER BY r.source, r.rowid"))
    if limit:
        sql += " LIMIT ? OFFSET ?"
        params += [limit, offset]
    return [dict(r) for r in conn.execute(sql, params)]


def summary_row(row: dict) -> dict:
    rec = json.loads(row["data"])
    leads = [o["name"] for o in rec.get("organizations") or [] if o.get("role") in LEADING_ROLES]
    people = [p.get("source_text") for p in rec.get("people") or [] if p.get("role") == "beneficiary"]
    region = rec.get("region") or {}
    funding = rec.get("funding") or {}
    return {
        "key": f"{row['source']}/{row['record_id']}",
        "source": row["source"],
        "title": row["title"],
        "beneficiary": "; ".join(x for x in (leads or people) if x),
        "voivodeships": region.get("voivodeships") or [],
        "country": region.get("country"),
        "programme": funding.get("programme"),
        "contest": funding.get("contest"),
        "quality": row["quality"],
        "first_seen": row["first_seen"],
        "changed_at": row["changed_at"],
        "removed_at": row["removed_at"],
        "category": row.get("category"),
    }


def get_record(conn: sqlite3.Connection, source: str, record_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM records WHERE source=? AND record_id=?", (source, record_id)).fetchone()
    if row is None:
        return None
    versions = conn.execute("SELECT content_hash, seen_at FROM record_versions WHERE source=? AND record_id=? "
                            "ORDER BY seen_at", (source, record_id)).fetchall()
    return {
        "record": json.loads(row["data"]),
        "history": {"first_seen": row["first_seen"], "last_seen": row["last_seen"], "changed_at": row["changed_at"],
                    "removed_at": row["removed_at"], "versions": [dict(v) for v in versions]},
    }


def stats(conn: sqlite3.Connection) -> dict:
    by = conn.execute("SELECT source, source_name, quality, category, removed_at IS NOT NULL AS removed, COUNT(*) n "
                      "FROM records GROUP BY 1, 2, 3, 4, 5").fetchall()
    out: dict = {"records": 0, "removed": 0, "sources": {}, "source_ids": {}, "quality": {}, "categories": {}}
    for r in by:
        if r["removed"]:
            out["removed"] += r["n"]
            continue
        out["records"] += r["n"]
        name = r["source_name"] or r["source"]
        out["sources"][name] = out["sources"].get(name, 0) + r["n"]
        out["source_ids"][r["source"]] = r["source_name"]
        q = r["quality"] or "(brak)"
        out["quality"][q] = out["quality"].get(q, 0) + r["n"]
        c = r["category"] or "(brak)"
        out["categories"][c] = out["categories"].get(c, 0) + r["n"]
    out["organizations"] = conn.execute("SELECT COUNT(*) FROM organizations").fetchone()[0]
    out["cards"] = conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
    out["fts"] = has_fts(conn)
    return out


def export_jsonl(conn: sqlite3.Connection, out: Path, source: str | None = None, include_removed: bool = False) -> int:
    rows = list_records(conn, source=source, include_removed=include_removed)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(r["data"] + "\n")
    return len(rows)


# --- CLI -----------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=None, help=f"plik bazy (domyślnie $RADAR_DB albo {DEFAULT_DB})")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="utwórz bazę i schemat")
    p = sub.add_parser("import", help="wczytaj pliki JSONL konektorów")
    p.add_argument("files", nargs="+")
    sub.add_parser("stats", help="podsumowanie zawartości")
    p = sub.add_parser("search", help="wyszukiwanie pełnotekstowe")
    p.add_argument("query")
    p.add_argument("--limit", type=int, default=20)
    p = sub.add_parser("export", help="zapisz rekordy do JSONL")
    p.add_argument("--out", required=True)
    p.add_argument("--source", default=None)
    p.add_argument("--include-removed", action="store_true")
    args = ap.parse_args(argv)

    conn = connect(args.db)
    if args.cmd == "init":
        print(f"baza gotowa: {args.db or default_db()} (FTS5: {'tak' if has_fts(conn) else 'nie'})", file=sys.stderr)
    elif args.cmd == "import":
        for f in args.files:
            for src, c in import_jsonl(conn, Path(f)).items():
                print(f"{f}: {src} {c}", file=sys.stderr)
    elif args.cmd == "stats":
        print(json.dumps(stats(conn), ensure_ascii=False, indent=1))
    elif args.cmd == "search":
        for r in list_records(conn, q=args.query, limit=args.limit):
            print(f"{r['source']}/{r['record_id']}\t{r['title']}")
    elif args.cmd == "export":
        n = export_jsonl(conn, Path(args.out), args.source, args.include_removed)
        print(f"zapisano {n} rekordów do {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
