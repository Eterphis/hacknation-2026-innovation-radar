"""Biblioteka Nauki (bibliotekanauki.pl, ICM UW) OAI-PMH -> normalized records.

Open substitute for Google Scholar (no API, scraping forbidden) and PAN dLibra (JS challenge on
ListRecords): article metadata from Polish scientific journals, harvested incrementally by datestamp.

Metadata formats checked live (.house/reports/data-access.md):
  * ``oai_openaire`` (default): Dublin Core + DataCite, has keywords (``datacite:subject``),
    per-author affiliation (free text), DOI as ``alternateIdentifier``, issue date;
  * ``oai_dc``: plain Dublin Core, no keywords and no affiliations, but journal/issue/pages
    in ``dc:source``. Both map to the same record; the journal name for ``oai_openaire`` comes
    from ListSets (one set = one journal), cached in the raw directory.

``datestamp`` moves when metadata change (2017 articles restamped in 2026), so a ``--from``
window catches edits too. Deleted records are counted and listed (``--deleted-out``) so the
caller can mark them removed; a harvest window is never complete, so do not let the store
mark missing records as removed (``upsert_source(..., mark_removed=False)``).

Run:  python -X utf8 -m radar.sources.bibliotekanauki --days 7 --out data/normalized/bibliotekanauki.jsonl
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterator
import xml.etree.ElementTree as ET

from .. import RECORD_SCHEMA
from ..crawl import oai
from ..http import Response
from ..text import clean_text, fold
from .ncbr import SUBUNIT_WORDS, org_type_hint

SOURCE = "bibliotekanauki"
SOURCE_NAME = "Biblioteka Nauki (bibliotekanauki.pl) – artykuły naukowe, OAI-PMH"
CATEGORY = "nauka"
CONNECTOR_VERSION = "0.1.0"
ENDPOINT = "https://bibliotekanauki.pl/api/oai/articles"
ARTICLE_URL = "https://bibliotekanauki.pl/articles/{}"
DEFAULT_PREFIX = "oai_openaire"
SUPPORTED_PREFIXES = ("oai_openaire", "oai_dc")
MIN_ABSTRACT_CHARS = 200
SETS_MAX_AGE_DAYS = 30

# ISO 639-2 (as the repository writes dc:language) -> ISO 639-1
LANGS = {"pol": "pl", "eng": "en", "ger": "de", "deu": "de", "fre": "fr", "fra": "fr", "rus": "ru", "ukr": "uk",
         "bel": "be", "cze": "cs", "ces": "cs", "slo": "sk", "slk": "sk", "ita": "it", "spa": "es", "lit": "lt",
         "hun": "hu", "lat": "la", "por": "pt", "srp": "sr", "hrv": "hr", "slv": "sl", "bul": "bg"}
DOI_RE = re.compile(r"(?:doi\.org/|doi:\s*)?(10\.\d{4,9}/\S+)", re.I)
ISSN_RE = re.compile(r"^\d{4}-\d{3}[\dXx]$")
CITY_RE = re.compile(r"^[A-ZŁŚŻŹĆŃÓĘĄ][\w\-]+(?:[ \-][A-ZŁŚŻŹĆŃÓĘĄa-z][\w\-]+){0,2}$")


# --- metadata -> plain fields ----------------------------------------------------
@dataclass
class Article:
    """Format-independent view of one record's metadata."""

    titles: list[tuple[str | None, str]] = field(default_factory=list)  # (lang, text)
    abstracts: list[tuple[str | None, str]] = field(default_factory=list)
    creators: list[dict] = field(default_factory=list)  # {name, affiliations: [...]}
    publishers: list[str] = field(default_factory=list)
    dates: list[str] = field(default_factory=list)
    url: str | None = None
    doi: str | None = None
    pdf: str | None = None
    sources: list[str] = field(default_factory=list)  # oai_dc: "Journal; 2017, 2; 9-59", ISSNs
    languages: list[str] = field(default_factory=list)
    rights: list[str] = field(default_factory=list)
    subjects: list[str] = field(default_factory=list)
    types: list[str] = field(default_factory=list)

    def to_json(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


def _lang(e: ET.Element) -> str | None:
    return e.get("{http://www.w3.org/XML/1998/namespace}lang") or None


def _doi(value: str) -> str | None:
    m = DOI_RE.search(value or "")
    return m.group(1).rstrip(".,;") if m and (value.lower().startswith(("10.", "doi")) or "doi.org/" in value) else None


def _add(seq: list, value) -> None:
    if value and value not in seq:
        seq.append(value)


def parse_article(meta: ET.Element) -> Article:
    """Read oai_dc or oai_openaire metadata by local element names (namespaces vary by format)."""
    a = Article()
    for e in meta.iter():
        name, text = oai.local(e.tag), clean_text(oai.text_of(e)) if len(e) == 0 else ""
        if name == "title" and text:
            _add(a.titles, (_lang(e), text))
        elif name == "description" and text:
            _add(a.abstracts, (_lang(e), text))
        elif name == "creator" and len(e) == 0 and text:  # oai_dc: <dc:creator>Name</dc:creator>
            a.creators.append({"name": text, "affiliations": []})
        elif name == "creator":  # oai_openaire: <datacite:creator><creatorName/><affiliation/>...
            cname = clean_text(oai.text_of(next(iter(oai.children(e, "creatorName")), None)))
            if cname:
                affs: list[str] = []
                for af in oai.children(e, "affiliation"):
                    _add(affs, clean_text(oai.text_of(af)))
                a.creators.append({"name": cname, "affiliations": affs})
        elif name == "publisher":
            _add(a.publishers, text)
        elif name == "date" and text and e.get("dateType") in (None, "Issued", "Available"):
            _add(a.dates, text)
        elif name in ("identifier", "alternateIdentifier") and text:
            kind = (e.get("identifierType") or e.get("alternateIdentifierType") or "").upper()
            if kind == "DOI" or (not kind and _doi(text)):
                a.doi = a.doi or (_doi(text) or text)
            elif text.startswith("http") and not text.endswith(".pdf"):
                a.url = a.url or text
        elif name == "file" and text:
            a.pdf = a.pdf or text
        elif name == "relation" and text.endswith(".pdf"):
            a.pdf = a.pdf or text
        elif name == "source":
            _add(a.sources, text)
        elif name == "language":
            _add(a.languages, text)
        elif name in ("rights", "licenseCondition"):
            _add(a.rights, text)
        elif name == "subject":
            _add(a.subjects, text)
        elif name in ("type", "resourceType"):
            _add(a.types, text)
    return a


# --- normalization helpers -------------------------------------------------------
def iso_lang(code: str | None) -> str | None:
    if not code:
        return None
    c = code.strip().lower()
    return LANGS.get(c, c if len(c) == 2 else None)


def pick(items: list[tuple[str | None, str]], prefer: list[str | None]) -> str | None:
    """First text in the preferred language order, else the first one."""
    for lang in prefer:
        for item_lang, text in items:
            if (item_lang or "").lower() == (lang or ""):
                return text
    return items[0][1] if items else None


def parse_source(sources: list[str]) -> dict:
    """oai_dc 'Przegląd Środkowo-Wschodni; 2017, 2; 9-59' + ISSNs -> journal, issue, pages, issn."""
    out = {"journal": None, "issue": None, "pages": None, "issn": []}
    for s in sources:
        if ISSN_RE.match(s):
            out["issn"].append(s.upper())
        elif out["journal"] is None:
            parts = [p.strip() for p in s.split(";")]
            out["journal"] = parts[0] or None
            out["issue"] = parts[1] if len(parts) > 1 and parts[1] else None
            out["pages"] = parts[2] if len(parts) > 2 and parts[2] else None
    return out


def licence_id(rights: list[str]) -> tuple[str, bool]:
    """('CC-BY-4.0', True) / ('all-rights-reserved', False) / ('unknown', False).
    The bool says whether the full text (PDF) may be processed; metadata always may."""
    for r in rights:
        f = fold(r)
        m = re.match(r"cc ([a-z\-]+)\s*:", f)
        if m:
            version = re.search(r"(\d\.\d)(\s*pl)?", f)
            ver = (version.group(1) + ("-PL" if version.group(2) else "")) if version else ""
            return "-".join(x for x in ("CC", m.group(1).upper(), ver) if x), True
        if "wszystkie prawa zastrzezone" in f or "all rights reserved" in f:
            return "all-rights-reserved", False
    return "unknown", False


def split_affiliation(raw: str) -> tuple[str, str | None]:
    """'Uniwersytet Przyrodniczy w Poznaniu, Poznań' -> ('Uniwersytet Przyrodniczy w Poznaniu', 'Poznań')."""
    head, sep, tail = raw.rpartition(",")
    tail = tail.strip()
    if (sep and head.strip() and CITY_RE.match(tail) and not org_type_hint(tail)
            and not (fold(tail) + " ").startswith(SUBUNIT_WORDS)):
        return head.strip(" ,"), tail
    return raw.strip(), None


def person_name(raw: str) -> dict:
    """'Kozlowski, K.' -> {name: 'K. Kozlowski', family: 'Kozlowski', given: 'K.'}."""
    family, sep, given = raw.partition(",")
    if sep and family.strip() and given.strip():
        return {"name": f"{given.strip()} {family.strip()}", "family": family.strip(), "given": given.strip()}
    return {"name": raw.strip(), "family": None, "given": None}


def record_id_of(identifier: str) -> str:
    """'oai:bibliotekanauki.pl:436948' -> '436948'."""
    return identifier.rsplit(":", 1)[-1] or identifier


def _year(dates: list[str]) -> int | None:
    for d in dates:
        m = re.match(r"(\d{4})", d)
        if m:
            return int(m.group(1))
    return None


# --- record ------------------------------------------------------------------------
def build_record(rec: oai.Record, *, metadata_prefix: str, page_url: str | None, fetched_at: str | None,
                 set_names: dict[str, str] | None = None, raw_page: str | None = None) -> dict:
    """One OAI record (not deleted) -> radar.record/v1."""
    if rec.metadata is None:
        raise ValueError(f"{rec.header.identifier} has no metadata (deleted?)")
    art = parse_article(rec.metadata)
    rid = record_id_of(rec.header.identifier)
    language = iso_lang(art.languages[0] if art.languages else None)
    prefer = ["pl", language, "en", None]
    title = pick(art.titles, prefer) or ""
    abstract = pick(art.abstracts, prefer)
    src = parse_source(art.sources)
    set_spec = rec.header.sets[0] if rec.header.sets else None
    journal = src["journal"] or (set_names or {}).get(set_spec or "")
    year = _year(art.dates)
    licence, fulltext_ok = licence_id(art.rights)
    keywords = list(dict.fromkeys(k for k in (clean_text(s).strip(" .") for s in art.subjects) if k))

    people, orgs, by_key = [], [], {}
    for c in art.creators:
        person = person_name(c["name"])
        people.append({**person, "role": "author", "source_text": c["name"], "affiliations": c["affiliations"]})
        for raw in c["affiliations"]:
            name, city = split_affiliation(raw)
            key = fold(name)
            if key not in by_key:
                by_key[key] = {"name": name, "role": "author_affiliation", "type_hint": org_type_hint(name),
                               "location": {"city": city}, "org_id": None, "is_public": None,
                               "source_text": raw, "authors": []}
                orgs.append(by_key[key])
            by_key[key]["authors"].append(person["name"])
    for pub in art.publishers:
        if fold(pub) not in by_key:
            orgs.append({"name": pub, "role": "publisher", "type_hint": org_type_hint(pub), "org_id": None,
                         "is_public": None})

    other_abstracts = {(lang or "?"): t for lang, t in art.abstracts if t != abstract}
    llm_parts = [f"Tytuł: {title}"]
    if abstract:
        llm_parts.append(f"Abstrakt:\n{abstract}")
    if keywords:
        llm_parts.append("Słowa kluczowe: " + ", ".join(keywords))
    affs = [o["name"] for o in orgs if o["role"] == "author_affiliation"]
    if affs:
        llm_parts.append("Afiliacje: " + "; ".join(affs))
    if journal:
        llm_parts.append(f"Czasopismo: {journal}" + (f" ({year})" if year else ""))

    blocking, warnings = [], []
    if not title:
        blocking.append("missing_title")
    if not abstract:
        blocking.append("missing_abstract")
    elif len(abstract) < MIN_ABSTRACT_CHARS:
        blocking.append("short_text")
    if not art.creators:
        warnings.append("no_authors")
    if not affs:
        warnings.append("no_affiliation" if metadata_prefix != "oai_dc" else "no_affiliation_in_oai_dc")
    if not keywords:
        warnings.append("no_keywords" if metadata_prefix != "oai_dc" else "no_keywords_in_oai_dc")
    if not art.doi:
        warnings.append("no_doi")
    if year is None:
        warnings.append("date_missing")

    content = art.to_json() | {"set": set_spec}
    content_hash = hashlib.sha256(json.dumps(content, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return {
        "schema": RECORD_SCHEMA,
        "source": SOURCE,
        "source_name": SOURCE_NAME,
        "record_id": rid,
        "url": art.url or ARTICLE_URL.format(rid),
        "list_url": ENDPOINT,
        "content_hash": content_hash,
        "record_type": "scientific_article",
        "language": language,
        "title": title,
        "intro": None,
        "text": {"abstract": abstract, "abstracts_other": other_abstracts, "other": []},
        "text_for_llm": "\n\n".join(llm_parts),
        "organizations": orgs,
        "people": people,
        "funding": {},
        "period": {"start": None, "end": None, "precision": None, "status": None, "ongoing": False, "raw": None},
        "region": {"voivodeships": [], "nationwide": False, "raw": None},
        "keywords": keywords,
        "publication": {
            "year": year,
            "date": art.dates[0] if art.dates else None,
            "journal": journal,
            "issue": src["issue"],
            "pages": src["pages"],
            "issn": src["issn"],
            "doi": art.doi,
            "pdf_url": art.pdf,
            "type": art.types[0] if art.types else None,
            "titles": {(lang or "?"): t for lang, t in art.titles},
        },
        "extra": {"category": CATEGORY, "set_spec": set_spec},
        "rights": {
            "licence": licence,
            "licence_text": art.rights[0] if art.rights else None,
            "llm_may_read_fulltext": fulltext_ok,
            "note": "Metadane (tytuł, abstrakt, słowa kluczowe) z OAI-PMH Biblioteki Nauki; "
                    "pełny tekst PDF tylko przy licencji CC.",
        },
        "quality": {
            "status": "needs_review" if blocking else "ok",
            "blocking": blocking,
            "warnings": warnings,
            "narrative_chars": len(abstract or ""),
        },
        "provenance": {
            "connector": f"radar.sources.bibliotekanauki/{CONNECTOR_VERSION}",
            "endpoint": ENDPOINT,
            "metadata_prefix": metadata_prefix,
            "oai_identifier": rec.header.identifier,
            "datestamp": rec.header.datestamp,
            "page_url": page_url,
            "list_fetched_at": fetched_at,
            "detail_fetched_at": None,
            "raw_page": raw_page,
        },
    }


# --- raw store + harvest -----------------------------------------------------------
class RawStore:
    """Raw OAI responses on disk, one directory per harvest window:
    ``<root>/<prefix>-<set>-<from>-<until>/page-0001.xml`` + ``run.json`` (pages, URLs, fetch times).
    ``latest.json`` names the last window, so ``--offline`` can rebuild without the network.
    ``sets.json`` caches ListSets (set id -> journal name)."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    @staticmethod
    def run_key(prefix: str, set_spec: str | None, from_: str | None, until: str | None) -> str:
        key = "-".join([prefix, set_spec or "all", from_ or "start", until or "now"])
        return re.sub(r"[^A-Za-z0-9_.-]+", "_", key)

    def save_page(self, key: str, n: int, page: oai.Page) -> str:
        d = self.root / key
        d.mkdir(parents=True, exist_ok=True)
        name = f"page-{n:04d}.xml"
        (d / name).write_text(page.text, "utf-8")
        run_path = d / "run.json"
        run = json.loads(run_path.read_text("utf-8")) if n > 1 and run_path.exists() else {"pages": []}
        run["pages"] = run["pages"][: n - 1] + [{"file": name, "url": page.url, "fetched_at": page.fetched_at,
                                                  "records": len(page.records), "token": page.token}]
        run_path.write_text(json.dumps(run, ensure_ascii=False, indent=1), "utf-8")
        (self.root / "latest.json").write_text(json.dumps({"run": key}), "utf-8")
        return f"{key}/{name}"

    def load_pages(self, key: str | None) -> tuple[str, list[oai.Page]]:
        if key is None or not (self.root / key / "run.json").exists():
            latest = self.root / "latest.json"
            if not latest.exists():
                raise FileNotFoundError(f"no cached OAI pages in {self.root} (run once online)")
            key = json.loads(latest.read_text("utf-8"))["run"]
        run = json.loads((self.root / key / "run.json").read_text("utf-8"))
        pages = []
        for p in run["pages"]:
            text = (self.root / key / p["file"]).read_text("utf-8")
            page = oai.parse_response(text, url=p.get("url", ""), fetched_at=p.get("fetched_at"))
            pages.append(page)
        return key, pages

    def load_sets(self, max_age_days: int | None = SETS_MAX_AGE_DAYS) -> dict[str, str] | None:
        path = self.root / "sets.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text("utf-8"))
        if max_age_days is not None:
            fetched = datetime.fromisoformat(data["fetched_at"])
            if datetime.now(timezone.utc) - fetched > timedelta(days=max_age_days):
                return None
        return data["sets"]

    def save_sets(self, sets: dict[str, str]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "sets.json").write_text(json.dumps(
            {"fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "sets": sets},
            ensure_ascii=False, indent=1), "utf-8")


@dataclass
class HarvestStats:
    pages: int = 0
    headers: int = 0
    records: int = 0
    deleted: list[str] = field(default_factory=list)
    skipped: int = 0  # live headers without metadata
    empty_reason: str | None = None
    status: Counter = field(default_factory=Counter)
    reasons: Counter = field(default_factory=Counter)
    warnings: Counter = field(default_factory=Counter)

    def summary(self) -> str:
        lines = [
            f"OAI pages: {self.pages}, headers: {self.headers}"
            + (f" ({self.empty_reason})" if self.empty_reason else ""),
            f"records: {self.records}, deleted in source: {len(self.deleted)}, skipped: {self.skipped}",
            "quality: " + ", ".join(f"{k}={v}" for k, v in self.status.most_common()),
        ]
        if self.reasons:
            lines.append("reasons: " + ", ".join(f"{k}={v}" for k, v in self.reasons.most_common()))
        if self.warnings:
            lines.append("warnings: " + ", ".join(f"{k}={v}" for k, v in self.warnings.most_common()))
        return "\n".join(lines)


def _sets(store: RawStore, *, fetcher, delay, offline: bool) -> dict[str, str]:
    cached = store.load_sets(max_age_days=None if offline else SETS_MAX_AGE_DAYS)
    if cached is not None or offline:
        return cached or {}
    try:
        sets = oai.list_sets(ENDPOINT, fetcher=fetcher, delay=delay)
    except Exception as e:  # journal names are a nicety; never fail the harvest on them
        print(f"warning: ListSets failed ({e}); journal names unavailable", file=sys.stderr)
        return store.load_sets(max_age_days=None) or {}
    store.save_sets(sets)
    return sets


def harvest(
    store: RawStore,
    *,
    fetcher: Callable[[str], Response] = oai.fetch_xml,
    metadata_prefix: str = DEFAULT_PREFIX,
    set_spec: str | None = None,
    from_: date | str | None = None,
    until: date | str | None = None,
    limit: int | None = None,
    delay: float = oai.DEFAULT_DELAY,
    offline: bool = False,
    with_sets: bool = True,
    stats: HarvestStats | None = None,
    sleep: Callable[[float], None] | None = None,
) -> Iterator[dict]:
    """Yield one normalized record per live OAI record in the window. Deleted ones go to
    ``stats.deleted`` (record ids). Pages are saved before their records are yielded."""
    if metadata_prefix not in SUPPORTED_PREFIXES:
        raise ValueError(f"metadata prefix {metadata_prefix!r} not mapped; use one of {SUPPORTED_PREFIXES}")
    stats = stats if stats is not None else HarvestStats()
    key = RawStore.run_key(metadata_prefix, set_spec, oai.oai_date(from_), oai.oai_date(until))
    set_names = _sets(store, fetcher=fetcher, delay=delay, offline=offline) if with_sets else {}

    if offline:
        key, cached = store.load_pages(key)
        pages: Iterator[tuple[str, oai.Page]] = ((f"{key}/page-{i:04d}.xml", p) for i, p in enumerate(cached, 1))
    else:
        kwargs = {"sleep": sleep} if sleep else {}
        live = oai.iter_pages(ENDPOINT, "ListRecords", metadata_prefix=metadata_prefix, set_spec=set_spec,
                              from_=from_, until=until, fetcher=fetcher, delay=delay, **kwargs)
        pages = ((store.save_page(key, i, p), p) for i, p in enumerate(live, 1))

    for raw_name, page in pages:
        stats.pages += 1
        stats.empty_reason = page.empty_reason or stats.empty_reason
        for rec in page.records:
            stats.headers += 1
            if rec.header.deleted:
                stats.deleted.append(record_id_of(rec.header.identifier))
                continue
            if rec.metadata is None:
                stats.skipped += 1
                continue
            record = build_record(rec, metadata_prefix=metadata_prefix, page_url=page.url,
                                  fetched_at=page.fetched_at, set_names=set_names, raw_page=raw_name)
            stats.records += 1
            stats.status[record["quality"]["status"]] += 1
            for r in record["quality"]["blocking"]:
                stats.reasons[r] += 1
            for w in record["quality"]["warnings"]:
                stats.warnings[w] += 1
            yield record
            if limit is not None and stats.records >= limit:
                return


CSV_COLUMNS = ["record_id", "title", "year", "journal", "authors", "affiliations", "keywords", "doi",
               "licence", "language", "quality", "reasons", "url"]


def _csv_row(r: dict) -> dict:
    pub = r["publication"]
    return {
        "record_id": r["record_id"],
        "title": r["title"],
        "year": pub["year"],
        "journal": pub["journal"],
        "authors": "; ".join(p["name"] for p in r["people"]),
        "affiliations": "; ".join(o["name"] for o in r["organizations"] if o["role"] == "author_affiliation"),
        "keywords": ", ".join(r["keywords"]),
        "doi": pub["doi"],
        "licence": r["rights"]["licence"],
        "language": r["language"],
        "quality": r["quality"]["status"],
        "reasons": "; ".join(r["quality"]["blocking"] + r["quality"]["warnings"]),
        "url": r["url"],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="data/normalized/bibliotekanauki.jsonl", help="JSONL output (one record per line)")
    ap.add_argument("--csv", default=None, help="optional CSV view for people")
    ap.add_argument("--raw-dir", default="data/raw/bibliotekanauki", help="where raw OAI pages are cached")
    ap.add_argument("--limit", type=int, default=None, help="stop after N records")
    ap.add_argument("--from", dest="from_", default=None,
                    help="harvest records changed since YYYY-MM-DD ('start' = whole repository)")
    ap.add_argument("--until", default=None, help="harvest records changed until YYYY-MM-DD")
    ap.add_argument("--days", type=int, default=7, help="without --from: window of the last N days (default 7)")
    ap.add_argument("--set", dest="set_spec", default=None, help="one OAI set (journal), e.g. 11")
    ap.add_argument("--prefix", default=DEFAULT_PREFIX, choices=SUPPORTED_PREFIXES, help="metadata format")
    ap.add_argument("--delay", type=float, default=oai.DEFAULT_DELAY, help="seconds between OAI requests")
    ap.add_argument("--no-sets", action="store_true", help="skip ListSets (no journal names for oai_openaire)")
    ap.add_argument("--deleted-out", default=None, help="write ids of records deleted in the source (one per line)")
    ap.add_argument("--offline", action="store_true", help="use cached raw pages only, no network")
    args = ap.parse_args(argv)

    if args.from_ == "start":
        from_ = None
    elif args.from_:
        from_ = args.from_
    else:
        from_ = (date.today() - timedelta(days=args.days)).isoformat()

    stats = HarvestStats()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    rows = []
    started = datetime.now(timezone.utc)
    with tmp.open("w", encoding="utf-8") as fh:
        for rec in harvest(RawStore(Path(args.raw_dir)), metadata_prefix=args.prefix, set_spec=args.set_spec,
                           from_=from_, until=args.until, limit=args.limit, delay=args.delay,
                           offline=args.offline, with_sets=not args.no_sets, stats=stats):
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            rows.append(_csv_row(rec))
            if stats.records % 100 == 0:
                print(f"... {stats.records} records", file=sys.stderr)
    tmp.replace(out)
    if args.csv:
        Path(args.csv).parent.mkdir(parents=True, exist_ok=True)
        with open(args.csv, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=CSV_COLUMNS, delimiter=";")
            w.writeheader()
            w.writerows(rows)
    if args.deleted_out:
        Path(args.deleted_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.deleted_out).write_text("".join(f"{i}\n" for i in stats.deleted), "utf-8")
    secs = (datetime.now(timezone.utc) - started).total_seconds()
    print(stats.summary(), file=sys.stderr)
    print(f"wrote {stats.records} records to {out} in {secs:.0f}s (window from {from_ or 'start'})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
