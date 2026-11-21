"""OpenAlex works with a Polish affiliation -> normalized records (replacement for Google Scholar).

Google Scholar has no API and its terms forbid scraping; OpenAlex (CC0 metadata) indexes the same
literature. The connector pages through https://api.openalex.org/works with
`filter=institutions.country_code:PL` and a cursor (`cursor=*`, up to 200 works per page).
One work = one record in category `nauka`.

Incremental runs: `--since YYYY-MM-DD` (or `--days N`, default 30) adds `from_publication_date`.
Because the window rolls, a run returns only a slice of the source: load it into the database
without marking missing records as removed.

Credentials come only from the environment, never from code or fixtures:
  OPENALEX_API_KEY   own key (free; its own daily budget instead of the budget shared per IP)
  OPENALEX_MAILTO    contact address for the "polite pool"
Both are stripped from every URL that is saved or printed.

Run:  python -X utf8 -m radar.sources.openalex --limit 50 --out data/normalized/openalex.jsonl
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import os
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Iterator
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .. import RECORD_SCHEMA
from ..http import FetchError, Response, fetch
from ..text import clean_text, fold
from .ncbr import org_type_hint

SOURCE = "openalex_pl"
SOURCE_NAME = "OpenAlex – prace z afiliacją w Polsce"
CONNECTOR_VERSION = "0.1.0"
CATEGORY = "nauka"
API_URL = "https://api.openalex.org/works"
COUNTRY = "PL"
MAX_PER_PAGE = 200
MIN_TEXT_CHARS = 200
MAX_PEOPLE = 50  # collaboration papers list thousands of authors
DEFAULT_DAYS = 30
SELECT = ("id,doi,title,display_name,publication_date,publication_year,type,language,"
          "abstract_inverted_index,authorships,topics,keywords,primary_location,open_access,"
          "cited_by_count,updated_date,grants,funders")
SECRET_PARAMS = {"api_key", "mailto"}
# fields that change without the work changing; left out of content_hash
VOLATILE = {"cited_by_count", "updated_date", "counts_by_year", "cited_by_api_url", "relevance_score"}

# OpenAlex institution.type -> type_hint used by the other connectors
INSTITUTION_TYPES = {
    "education": "university",
    "facility": "research_institute",
    "company": "company",
    "government": "public_administration",
    "healthcare": "hospital",
    "nonprofit": "ngo",
    "funder": "other_org",
    "archive": "other_org",
    "other": "other_org",
}


class FormatChanged(Exception):
    """The API response no longer has the shape this connector expects."""


# --- helpers -------------------------------------------------------------------
def redact(url: str) -> str:
    """Drop api_key / mailto from a URL before it is saved or printed."""
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k not in SECRET_PARAMS]
    return urlunsplit(parts._replace(query=urlencode(query, safe=":,*")))


def redact_text(text: str) -> str:
    """Same for free text (error messages that embed a URL)."""
    return re.sub(r"\b(api_key|mailto)=[^&\s]*", r"\1=***", text)


def build_filter(since: str | None = None, require_abstract: bool = True, extra: str | None = None) -> str:
    parts = [f"institutions.country_code:{COUNTRY}"]
    if since:
        parts.append(f"from_publication_date:{since}")
    if require_abstract:
        parts.append("has_abstract:true")
    if extra:
        parts.append(extra)
    return ",".join(parts)


def page_url(cursor: str, *, filt: str, per_page: int = MAX_PER_PAGE, mailto: str | None = None,
             api_key: str | None = None, select: str | None = SELECT) -> str:
    params = {"filter": filt, "per-page": str(max(1, min(per_page, MAX_PER_PAGE))), "cursor": cursor}
    if select:
        params["select"] = select
    if mailto:
        params["mailto"] = mailto
    if api_key:
        params["api_key"] = api_key
    return f"{API_URL}?{urlencode(params, safe=':,*')}"


def short_id(openalex_id: str | None) -> str | None:
    """'https://openalex.org/W4401234567' -> 'W4401234567'."""
    return openalex_id.rstrip("/").rsplit("/", 1)[-1] if openalex_id else None


def strip_markup(text: str | None) -> str:
    """Titles and abstracts carry HTML entities and inline tags (<i>, <sub>, <jats:p>)."""
    if not text:
        return ""
    text = re.sub(r"<[^>]{1,200}>", " ", text)
    return clean_text(re.sub(r"[ \t]+", " ", html.unescape(text)))


def abstract_from_inverted_index(index: dict[str, list[int]] | None) -> str:
    """{'Ala': [0], 'ma': [1, 3], 'kota': [2]} -> 'Ala ma kota ma'."""
    if not index:
        return ""
    positions: dict[int, str] = {}
    for word, places in index.items():
        for p in places or []:
            if isinstance(p, int) and p >= 0:
                positions.setdefault(p, word)
    text = " ".join(positions[p] for p in sorted(positions))
    return strip_markup(text)


def _doi_url(doi: str | None) -> str | None:
    if not doi:
        return None
    return doi if doi.startswith("http") else f"https://doi.org/{doi}"


def _bare_doi(doi: str | None) -> str | None:
    return re.sub(r"^https?://(dx\.)?doi\.org/", "", doi, flags=re.I) if doi else None


def _ror(ror: str | None) -> str | None:
    return ror or None


# --- normalization -------------------------------------------------------------
def organizations(work: dict) -> list[dict]:
    """Unique institutions from authorships[].institutions, Polish ones first."""
    found: dict[str, dict] = {}
    for a in work.get("authorships") or []:
        for inst in a.get("institutions") or []:
            name = clean_text(inst.get("display_name") or "")
            if not name:
                continue
            key = inst.get("id") or fold(name)
            if key in found:
                continue
            cc = inst.get("country_code")
            found[key] = {
                "name": name,
                "role": "affiliation",
                "type_hint": INSTITUTION_TYPES.get(inst.get("type") or "") or org_type_hint(name),
                "org_id": _ror(inst.get("ror")),
                "openalex_id": short_id(inst.get("id")),
                "country": cc,
                "location": {"country": cc},
                "is_public": None,
            }
    orgs = list(found.values())
    orgs.sort(key=lambda o: o["country"] != COUNTRY)  # stable: keeps author order within groups
    return orgs


def people(work: dict) -> tuple[list[dict], bool]:
    out = []
    authorships = work.get("authorships") or []
    for a in authorships[:MAX_PEOPLE]:
        author = a.get("author") or {}
        name = clean_text(author.get("display_name") or a.get("raw_author_name") or "")
        if not name:
            continue
        out.append({
            "name": name,
            "role": "author",
            "source_text": a.get("raw_author_name") or name,
            "position": a.get("author_position"),
            "corresponding": bool(a.get("is_corresponding")),
            "orcid": author.get("orcid"),
            "institutions": [clean_text(i.get("display_name") or "") for i in a.get("institutions") or []
                             if i.get("display_name")],
        })
    return out, len(authorships) > MAX_PEOPLE


def topics(work: dict) -> list[dict]:
    out = []
    for t in work.get("topics") or []:
        out.append({
            "name": t.get("display_name"),
            "score": t.get("score"),
            "subfield": (t.get("subfield") or {}).get("display_name"),
            "field": (t.get("field") or {}).get("display_name"),
            "domain": (t.get("domain") or {}).get("display_name"),
        })
    return out


def keywords(work: dict) -> list[str]:
    words = [k.get("display_name") for k in work.get("keywords") or []]
    for t in topics(work):
        words += [t["name"], t["subfield"], t["field"]]
    seen: dict[str, str] = {}
    for w in words:
        w = clean_text(w or "")
        if w and fold(w) not in seen:
            seen[fold(w)] = w
    return list(seen.values())


def funders(work: dict) -> tuple[list[str], list[dict]]:
    names: list[str] = []
    awards: list[dict] = []
    for g in work.get("grants") or []:
        name = g.get("funder_display_name")
        if name:
            names.append(name)
        if g.get("award_id"):
            awards.append({"funder": name, "award_id": g["award_id"]})
    for f in work.get("funders") or []:
        if f.get("display_name"):
            names.append(f["display_name"])
    return list(dict.fromkeys(names)), awards


def content_hash(work: dict) -> str:
    stable = {k: v for k, v in work.items() if k not in VOLATILE}
    return hashlib.sha256(json.dumps(stable, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def build_record(work: dict, *, fetched_at: str | None = None, page_url_redacted: str | None = None,
                 page_no: int | None = None, row: int | None = None, raw_files: dict | None = None,
                 api_filter: str | None = None) -> dict:
    wid = short_id(work.get("id"))
    if not wid:
        raise FormatChanged("praca bez pola 'id'")
    title = strip_markup(work.get("title") or work.get("display_name"))
    abstract = abstract_from_inverted_index(work.get("abstract_inverted_index"))
    orgs = organizations(work)
    authors, truncated = people(work)
    kw = keywords(work)
    funder_names, awards = funders(work)
    loc = work.get("primary_location") or {}
    venue = loc.get("source") or {}
    oa = work.get("open_access") or {}
    doi_url = _doi_url(work.get("doi"))
    pub_date = work.get("publication_date")
    pl_orgs = [o["name"] for o in orgs if o["country"] == COUNTRY]

    text_for_llm = "\n\n".join(x for x in [
        f"Tytuł: {title}",
        f"Abstrakt:\n{abstract}" if abstract else "",
        f"Słowa kluczowe: {', '.join(kw)}" if kw else "",
        f"Czasopismo / źródło: {venue['display_name']}" if venue.get("display_name") else "",
        f"Afiliacje w Polsce: {'; '.join(pl_orgs)}" if pl_orgs else "",
        f"Finansowanie: {'; '.join(funder_names)}" if funder_names else "",
    ] if x)

    blocking, warnings = [], []
    if not title:
        blocking.append("missing_title")
    if not abstract:
        blocking.append("missing_abstract")
    elif len(abstract) < MIN_TEXT_CHARS:
        blocking.append("short_text")
    if not pl_orgs:
        warnings.append("no_polish_institution")
    if truncated:
        warnings.append("authors_truncated")
    if not pub_date:
        warnings.append("missing_publication_date")

    return {
        "schema": RECORD_SCHEMA,
        "source": SOURCE,
        "source_name": SOURCE_NAME,
        "record_id": wid,
        "url": doi_url or loc.get("landing_page_url") or work.get("id"),
        "list_url": API_URL,
        "content_hash": content_hash(work),
        "record_type": "scientific_publication",
        "language": work.get("language"),
        "title": title,
        "intro": None,
        "text": {"description": abstract or None, "other": []},
        "text_for_llm": text_for_llm,
        "organizations": orgs,
        "people": authors,
        "funding": {
            "operator": None,
            "programme": None,
            "contest": None,
            "project_no": None,
            "funders": funder_names,
            "awards": awards,
            "total_value": None,
            "grant_value": None,
            "currency": None,
        },
        "period": {
            "start": pub_date,
            "end": None,
            "precision": "day" if pub_date else None,
            "status": None,
            "ongoing": False,
            "raw": f"data publikacji: {pub_date}" if pub_date else None,
        },
        "region": {"voivodeships": [], "nationwide": False, "raw": None, "country": COUNTRY},
        "keywords": kw,
        "extra": {
            "category": CATEGORY,
            "openalex_id": wid,
            "doi": _bare_doi(work.get("doi")),
            "work_type": work.get("type"),
            "publication_date": pub_date,
            "publication_year": work.get("publication_year"),
            "venue": venue.get("display_name"),
            "venue_issn_l": venue.get("issn_l"),
            "venue_type": venue.get("type"),
            "landing_page_url": loc.get("landing_page_url"),
            "content_licence": loc.get("license"),
            "open_access": {"is_oa": oa.get("is_oa"), "status": oa.get("oa_status"), "url": oa.get("oa_url")},
            "cited_by_count": work.get("cited_by_count"),
            "updated_date": work.get("updated_date"),
            "topics": topics(work),
        },
        "rights": {
            "licence": "CC0-1.0",
            "llm_may_read_fulltext": True,
            "note": "Metadane OpenAlex na licencji CC0; abstrakt odtworzony z abstract_inverted_index może "
                    "podlegać prawom wydawcy (licencja treści w extra.content_licence).",
        },
        "quality": {
            "status": "needs_review" if blocking else "ok",
            "blocking": blocking,
            "warnings": warnings,
            "narrative_chars": len(abstract),
        },
        "provenance": {
            "connector": f"radar.sources.openalex/{CONNECTOR_VERSION}",
            "list_fetched_at": fetched_at,
            "detail_fetched_at": None,
            "source_file_url": page_url_redacted,
            "source_page": page_no,
            "source_row": row,
            "api_filter": api_filter,
            "raw_files": raw_files or {},
        },
    }


# --- raw store + harvest -------------------------------------------------------
class RawStore:
    """pages/page-0001.json (raw API body) + page-0001.meta.json (redacted URL, cursor, time)."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.pages = self.root / "pages"

    def reset(self) -> None:
        """A new online run replaces the previous run's pages (only files this store wrote)."""
        if self.pages.exists():
            for p in self.pages.glob("page-*.json"):
                p.unlink()

    def save_page(self, no: int, resp: Response, *, cursor: str, api_filter: str) -> dict:
        self.pages.mkdir(parents=True, exist_ok=True)
        path = self.pages / f"page-{no:04d}.json"
        path.write_text(resp.text, "utf-8")
        meta = {"page": no, "url": redact(resp.url), "status": resp.status, "fetched_at": resp.fetched_at,
                "cursor": cursor, "filter": api_filter, "path": path.name}
        (self.pages / f"page-{no:04d}.meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), "utf-8")
        return {**meta, "path": str(path)}

    def load_pages(self) -> Iterator[tuple[dict, str]]:
        for meta_path in sorted(self.pages.glob("page-*.meta.json")):
            meta = json.loads(meta_path.read_text("utf-8"))
            body = self.pages / re.split(r"[\\/]", meta["path"])[-1]
            yield {**meta, "path": str(body)}, body.read_text("utf-8")


@dataclass
class HarvestStats:
    pages: int = 0
    works: int = 0
    records: int = 0
    duplicates: int = 0
    total_available: int | None = None
    api_filter: str | None = None
    status: Counter = field(default_factory=Counter)
    reasons: Counter = field(default_factory=Counter)

    def summary(self) -> str:
        lines = [f"filter: {self.api_filter}", f"available in OpenAlex: {self.total_available}",
                 f"pages: {self.pages}, works: {self.works}, records: {self.records} (duplicates skipped: {self.duplicates})",
                 "quality: " + ", ".join(f"{k}={v}" for k, v in self.status.most_common())]
        if self.reasons:
            lines.append("reasons: " + ", ".join(f"{k}={v}" for k, v in self.reasons.most_common()))
        return "\n".join(lines)


def _parse_page(text: str) -> dict:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise FormatChanged(f"odpowiedź OpenAlex nie jest JSON-em: {e}") from e
    if not isinstance(data, dict) or not isinstance(data.get("results"), list) or "meta" not in data:
        raise FormatChanged("odpowiedź OpenAlex bez pól 'meta' i 'results'")
    return data


def _pages_online(store: RawStore, fetcher, *, api_filter: str, limit: int | None, max_pages: int | None,
                  mailto: str | None, api_key: str | None, delay: float, sleep) -> Iterator[tuple[dict, str]]:
    store.reset()
    cursor, no, got, select = "*", 0, 0, SELECT
    while cursor and (max_pages is None or no < max_pages) and (limit is None or got < limit):
        if no:
            sleep(delay)
        per_page = MAX_PER_PAGE if limit is None else min(MAX_PER_PAGE, limit - got)
        try:
            resp = fetcher(page_url(cursor, filt=api_filter, per_page=per_page, mailto=mailto, api_key=api_key,
                                    select=select))
        except FetchError as e:
            if not (select and "HTTP 400" in str(e)):
                raise FetchError(redact_text(str(e))) from None
            # a field in SELECT was renamed or dropped by the API: fall back to full works
            select = None
            sleep(delay)
            try:
                resp = fetcher(page_url(cursor, filt=api_filter, per_page=per_page, mailto=mailto, api_key=api_key,
                                        select=None))
            except FetchError as e2:
                raise FetchError(redact_text(str(e2))) from None
        no += 1
        meta = store.save_page(no, resp, cursor=cursor, api_filter=api_filter)
        yield meta, resp.text
        data = _parse_page(resp.text)
        got += len(data["results"])
        cursor = (data.get("meta") or {}).get("next_cursor")
        if not data["results"]:
            break


def harvest(store: RawStore, *, page_fetcher: Callable[[str], Response] = fetch, offline: bool = False,
            limit: int | None = None, since: str | None = None, require_abstract: bool = True,
            extra_filter: str | None = None, max_pages: int | None = None, mailto: str | None = None,
            api_key: str | None = None, delay: float = 1.0, sleep: Callable[[float], None] = time.sleep,
            stats: HarvestStats | None = None) -> Iterator[dict]:
    stats = stats if stats is not None else HarvestStats()
    api_filter = build_filter(since, require_abstract, extra_filter)
    if offline:
        pages = store.load_pages()
    else:
        pages = _pages_online(store, page_fetcher, api_filter=api_filter, limit=limit, max_pages=max_pages,
                              mailto=mailto, api_key=api_key, delay=delay, sleep=sleep)
    seen: set[str] = set()
    for meta, text in pages:
        data = _parse_page(text)
        stats.pages += 1
        stats.api_filter = meta.get("filter") or api_filter
        stats.total_available = (data.get("meta") or {}).get("count", stats.total_available)
        for row, work in enumerate(data["results"], 1):
            if limit is not None and stats.records >= limit:
                return
            stats.works += 1
            rec = build_record(work, fetched_at=meta.get("fetched_at"), page_url_redacted=meta.get("url"),
                               page_no=meta.get("page"), row=row, raw_files={"page": meta.get("path")},
                               api_filter=stats.api_filter)
            if rec["record_id"] in seen:
                stats.duplicates += 1
                continue
            seen.add(rec["record_id"])
            stats.records += 1
            stats.status[rec["quality"]["status"]] += 1
            for r in rec["quality"]["blocking"]:
                stats.reasons[r] += 1
            yield rec


CSV_COLUMNS = ["record_id", "title", "publication_date", "work_type", "venue", "doi", "polish_institutions",
               "keywords", "cited_by", "open_access", "quality", "reasons"]


def _csv_row(r: dict) -> dict:
    ex = r["extra"]
    return {
        "record_id": r["record_id"], "title": r["title"], "publication_date": ex["publication_date"],
        "work_type": ex["work_type"], "venue": ex["venue"], "doi": ex["doi"],
        "polish_institutions": "; ".join(o["name"] for o in r["organizations"] if o["country"] == COUNTRY),
        "keywords": "; ".join(r["keywords"][:8]), "cited_by": ex["cited_by_count"],
        "open_access": ex["open_access"]["status"], "quality": r["quality"]["status"],
        "reasons": "; ".join(r["quality"]["blocking"] + r["quality"]["warnings"]),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="data/normalized/openalex.jsonl")
    ap.add_argument("--csv", default=None)
    ap.add_argument("--raw-dir", default="data/raw/openalex")
    ap.add_argument("--offline", action="store_true", help="use the saved API pages only, no network")
    ap.add_argument("--limit", type=int, default=None, help="stop after N records")
    ap.add_argument("--since", default=None, help="from_publication_date (YYYY-MM-DD); overrides --days")
    ap.add_argument("--days", type=int, default=DEFAULT_DAYS,
                    help=f"publication window in days when --since is not given (default {DEFAULT_DAYS}, 0 = no window)")
    ap.add_argument("--with-empty-abstracts", action="store_true", help="do not add has_abstract:true")
    ap.add_argument("--filter", default=None, help="extra OpenAlex filter, e.g. type:article")
    ap.add_argument("--max-pages", type=int, default=None)
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between API pages")
    args = ap.parse_args(argv)

    since = args.since
    if since is None and args.days:
        since = (date.today() - timedelta(days=args.days)).isoformat()
    stats = HarvestStats()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    rows = []
    try:
        with tmp.open("w", encoding="utf-8") as fh:
            for rec in harvest(RawStore(Path(args.raw_dir)), offline=args.offline, limit=args.limit, since=since,
                               require_abstract=not args.with_empty_abstracts, extra_filter=args.filter,
                               max_pages=args.max_pages, mailto=os.environ.get("OPENALEX_MAILTO") or None,
                               api_key=os.environ.get("OPENALEX_API_KEY") or None, delay=args.delay, stats=stats):
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
                rows.append(_csv_row(rec))
    except FetchError as e:
        tmp.unlink(missing_ok=True)
        print(f"OpenAlex: {e}", file=sys.stderr)
        if "429" in str(e):
            print("Wyczerpany limit zapytań. Ustaw OPENALEX_API_KEY (darmowy klucz z własnym budżetem) "
                  "albo spróbuj po północy UTC.", file=sys.stderr)
        return 2
    tmp.replace(out)
    if args.csv:
        with open(args.csv, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=CSV_COLUMNS, delimiter=";")
            w.writeheader()
            w.writerows(rows)
    print(stats.summary(), file=sys.stderr)
    print(f"wrote {stats.records} records to {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
