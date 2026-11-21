"""RAD-on open data (POL-on): research projects with abstracts + the institution registry -> records.

API (checked 2026-11-21, version "1.13.0", no key, no sign-up):

  GET https://radon.nauka.gov.pl/opendata/polon/projects?resultNumbers=100[&token=...]
  GET https://radon.nauka.gov.pl/opendata/polon/institutions?resultNumbers=100[&token=...]

  * Response: {"results": [...], "pagination": {"maxCount": N, "token": "..."}, "version": "1.13.0"}.
  * `resultNumbers` must be <= 100 (101 -> HTTP 400 "Requested results size must be smaller than 100").
  * Paging by `token`: pass the token from the previous page. The token is base64 of the last record's
    `lastRefresh` (ms since epoch), so pages run in ascending `lastRefresh` order. The last page still
    carries a token; it is the one with fewer than `resultNumbers` results (or none).
  * projects: ~48,850 Polish national projects (NCN, NCBR, NAWA, FNP, ABM, MNiSW programmes...), ~490
    pages at ~3 s each. Fields used here: projectUuid, projectNumber, projectTitlePl/En,
    projectAbstractPl/En, keywords (comma separated), disciplines, projectStartDate/EndDate/GrantDate,
    totalFunds/nationalFunds/foreignFunds (strings, PLN), projectClassification (OPUS, PRELUDIUM, ...),
    edition, financingInstitutions[] (financingInstitutionName, kindOfFinancingInstitution, ...),
    implementingInstitutions[] (institutionUuid, institutionName, leader "Tak"/"Nie"),
    receivedFunds[] (per implementing institution), projectManagers[] (name, role, ORCID), lastRefresh.
    **Server-side filters by financing/implementing institution are ignored** (only `projectTitlePl`
    filters), so the funder filter (NCN, NCBR) is applied locally after download.
  * institutions: 841 universities and research institutes (iKindName: "Uczelnia publiczna",
    "Uczelnia niepubliczna", "Uczelnia kościelna", "Instytucja naukowa", "Federacja"; siTypeName for
    institutes: "instytut badawczy", "instytut naukowy PAN", "instytut Sieci Łukasiewicz", ...) with
    regon, nip, krs, voivodeship, city, status (Działająca / W likwidacji / Zlikwidowana / ...), names[].
    `implementingInstitutions[].institutionUuid` matches `institutionUuid` here for universities and
    institutes; companies, hospitals and foreign partners are not in the registry (no REGON/NIP then).
  * /opendata/polon/patents: 404 (no patents in RAD-on open data).

Output:
  * one record per project financed by a selected funder (default NCN and NCBR, option --funder),
    source `radon_projects`;
  * the institution registry as JSONL next to --out (`<stem>_institutions.jsonl`), also used to enrich
    the organisations in records (REGON, NIP, KRS, type, public/private, voivodeship).

Category: the source goes into the database with category `projekty` (one category per source in
`radar/store.py`). Each record also carries `extra.category`: `nauka` for projects financed only by NCN
(basic research grants: OPUS, PRELUDIUM, SONATA...), `projekty` for NCBR (applied R&D, often with
companies). Splitting NCN into `nauka` in the database needs either per-record categories in the store
or a second source id; the record already holds what is needed for both.

Run:  python -X utf8 -m radar.sources.radon --out data/normalized/radon.jsonl
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable, Iterator
from urllib.parse import quote

from .. import RECORD_SCHEMA
from ..http import Response, fetch_bytes
from ..text import clean_text, fold
from .ncbr import org_type_hint

SOURCE = "radon_projects"
SOURCE_NAME = "RAD-on (POL-on) – projekty badawcze"
CONNECTOR_VERSION = "0.1.0"
API_BASE = "https://radon.nauka.gov.pl/opendata/polon/"
PROJECTS_URL = API_BASE + "projects"
INSTITUTIONS_URL = API_BASE + "institutions"
PAGE_SIZE = 100  # API maximum
MIN_TEXT_CHARS = 200

# funder key -> (short name, category, folded name prefixes)
FUNDERS: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "ncn": ("NCN", "nauka", ("narodowe centrum nauki",)),
    "ncbr": ("NCBR", "projekty", ("narodowe centrum badan i rozwoju",)),
}
DEFAULT_FUNDERS = ("ncn", "ncbr")
PUBLIC_INSTITUTE_TYPES = ("instytut badawczy", "instytut naukowy pan", "instytut sieci lukasiewicz",
                          "polska akademia umiejetnosci")


def fetch_json(url: str) -> Response:
    """GET with the project User-Agent and retries. Uses fetch_bytes (Accept: */*) because the API
    answers HTTP 406 to the HTML Accept header sent by http.fetch()."""
    resp = fetch_bytes(url, timeout=120.0)
    return Response(url=resp.url, status=resp.status, text=resp.content.decode("utf-8", errors="replace"),
                    fetched_at=resp.fetched_at)


def page_url(base: str, token: str | None) -> str:
    return f"{base}?resultNumbers={PAGE_SIZE}" + (f"&token={quote(token, safe='')}" if token else "")


# --- institutions ----------------------------------------------------------------
def normalize_institution(raw: dict) -> dict:
    """One registry entry -> compact dictionary row."""
    kind = raw.get("iKindName") or None
    subtype = raw.get("siTypeName") or raw.get("uTypeName") or None
    fk, fs = fold(kind or ""), fold(subtype or "")
    if fk.startswith("uczelnia"):
        type_hint = "university"
    elif fk == "instytucja naukowa":
        type_hint = "research_institute"
    else:
        type_hint = org_type_hint(raw.get("name") or "") or "other_org"
    if fk == "uczelnia publiczna" or fs in PUBLIC_INSTITUTE_TYPES:
        is_public: bool | None = True
    elif fk in ("uczelnia niepubliczna", "uczelnia koscielna"):
        is_public = False
    else:
        is_public = None
    names = [n.get("name", "").strip() for n in raw.get("names") or [] if n.get("name")]
    return {
        "uuid": raw.get("institutionUuid"),
        "name": (raw.get("name") or "").strip(),
        "regon": raw.get("regon") or None,
        "nip": raw.get("nip") or None,
        "krs": raw.get("krs") or None,
        "kind": kind,
        "subtype": subtype,
        "type_hint": type_hint,
        "is_public": is_public,
        "status": raw.get("status") or None,
        "voivodeship": raw.get("voivodeship") or None,
        "city": raw.get("city") or None,
        "www": raw.get("www") or None,
        "former_names": list(dict.fromkeys(n for n in names if n != (raw.get("name") or "").strip())),
        "last_refresh": raw.get("lastRefresh"),
    }


def institution_index(raw_institutions: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for raw in raw_institutions:
        inst = normalize_institution(raw)
        if inst["uuid"]:
            out[inst["uuid"]] = inst
    return out


# --- projects --------------------------------------------------------------------
def _num(value) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(" ", "").replace(",", "."))
    except ValueError:
        return None


def _iso(value) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None


def project_funders(raw: dict) -> list[str]:
    names = [f.get("financingInstitutionName") for f in raw.get("financingInstitutions") or []]
    names += [f.get("financingInstitutionName") for f in raw.get("receivedFunds") or []]
    return list(dict.fromkeys(n.strip() for n in names if n and n.strip()))


def funder_keys(raw: dict) -> list[str]:
    """Funder keys (FUNDERS) found among the project's financing institutions."""
    folded = [fold(n) for n in project_funders(raw)]
    return [k for k, (_, _, prefixes) in FUNDERS.items() if any(f.startswith(prefixes) for f in folded)]


def split_keywords(raw: str | None) -> list[str]:
    if not raw:
        return []
    parts = (clean_text(p).strip(" .") for p in re.split(r"[,;\n]", raw))
    return list(dict.fromkeys(p for p in parts if p))


def build_org(impl: dict, institutions: dict[str, dict], funds: dict[str, float | None]) -> tuple[dict, bool]:
    uuid = impl.get("institutionUuid")
    name = (impl.get("institutionName") or "").strip()
    inst = institutions.get(uuid or "")
    org = {
        "name": name,
        "role": "beneficiary" if impl.get("leader") == "Tak" else "partner",
        "type_hint": inst["type_hint"] if inst else org_type_hint(name),
        "org_id": None,
        "is_public": inst["is_public"] if inst else None,
        "radon_uuid": uuid,
        "regon": inst["regon"] if inst else None,
        "nip": inst["nip"] if inst else None,
        "krs": inst["krs"] if inst else None,
        "kind": inst["kind"] if inst else None,
        "subtype": inst["subtype"] if inst else None,
        "location": {"voivodeship": inst["voivodeship"], "city": inst["city"]} if inst else None,
        "in_registry": bool(inst),
        "received_funds": funds.get(uuid or ""),
    }
    return org, bool(inst)


def build_record(raw: dict, institutions: dict[str, dict], *, page_fetched_at: str | None,
                 page_file: str | None = None, today: date | None = None) -> dict:
    today = today or date.today()
    title_pl = clean_text(raw.get("projectTitlePl") or "")
    title_en = clean_text(raw.get("projectTitleEn") or "")
    title = title_pl or title_en
    abs_pl = clean_text(raw.get("projectAbstractPl") or "")
    abs_en = clean_text(raw.get("projectAbstractEn") or "")
    abstract = abs_pl or abs_en
    keywords = split_keywords(raw.get("keywords"))
    disciplines = list(dict.fromkeys(d.get("disciplineName") for d in raw.get("disciplines") or []
                                     if d.get("disciplineName")))

    funds = {f.get("institutionUuid"): _num(f.get("totalFunds")) for f in raw.get("receivedFunds") or []}
    orgs, unmatched = [], 0
    for impl in raw.get("implementingInstitutions") or []:
        org, matched = build_org(impl, institutions, funds)
        if org["name"]:
            orgs.append(org)
            unmatched += 0 if matched else 1
    orgs.sort(key=lambda o: o["role"] != "beneficiary")  # leader first
    people = []
    for m in raw.get("projectManagers") or []:
        name = " ".join(x for x in (m.get("firstName"), m.get("middleName"), m.get("lastName")) if x)
        if name:
            people.append({"name": name, "role": m.get("kindManager"), "orcid": m.get("ORCID") or None,
                           "organization": m.get("institutionName")})

    keys = funder_keys(raw)
    funders = project_funders(raw)
    operator = "/".join(FUNDERS[k][0] for k in keys) or (funders[0] if funders else None)
    category = "nauka" if keys == ["ncn"] else "projekty"

    start, end = _iso(raw.get("projectStartDate")), _iso(raw.get("projectEndDate"))
    if end and end < today:
        status = "finished"
    elif start and start > today:
        status = "planned"
    elif start:
        status = "running"
    else:
        status = None

    voivs = list(dict.fromkeys(o["location"]["voivodeship"] for o in orgs
                               if o.get("location") and o["location"].get("voivodeship")))
    total = _num(raw.get("totalFunds"))
    programme = raw.get("projectClassification") or None
    if programme == "Inna":
        programme = raw.get("anotherProjectClassification") or programme

    text_for_llm = "\n\n".join(x for x in [
        f"Tytuł: {title}",
        f"Tytuł (EN): {title_en}" if title_en and title_en != title else "",
        f"Streszczenie:\n{abs_pl}" if abs_pl else "",
        f"Abstract (EN):\n{abs_en}" if abs_en and not abs_pl else "",
        f"Słowa kluczowe: {', '.join(keywords)}" if keywords else "",
        f"Dyscypliny: {', '.join(disciplines)}" if disciplines else "",
    ] if x)

    blocking, warnings = [], []
    if not title:
        blocking.append("missing_title")
    if len(abstract) < MIN_TEXT_CHARS:
        blocking.append("short_text")
    if abs_en and not abs_pl:
        warnings.append("abstract_en_only")
    if not start:
        warnings.append("period_missing")
    if raw.get("totalFunds") and total is None:
        warnings.append("total_value_unparsed")
    if not any(o["role"] == "beneficiary" for o in orgs):
        warnings.append("no_leader")
    if unmatched:
        warnings.append(f"orgs_not_in_registry:{unmatched}")

    hashed = {k: v for k, v in raw.items() if k != "lastRefresh"}
    content_hash = hashlib.sha256(json.dumps({"raw": hashed, "orgs": orgs}, ensure_ascii=False,
                                             sort_keys=True).encode()).hexdigest()
    return {
        "schema": RECORD_SCHEMA,
        "source": SOURCE,
        "source_name": SOURCE_NAME,
        "record_id": raw.get("projectUuid") or "nr-" + re.sub(r"\W+", "-", raw.get("projectNumber") or ""),
        "url": None,  # open data has no per-project page; see list_url and provenance
        "list_url": PROJECTS_URL,
        "content_hash": content_hash,
        "record_type": "research_project",
        "language": "pl" if abs_pl or title_pl else "en",
        "title": title,
        "intro": None,
        "text": {"abstract": abs_pl or None, "abstract_en": abs_en or None, "title_en": title_en or None,
                 "other": []},
        "text_for_llm": text_for_llm,
        "organizations": orgs,
        "people": people,
        "funding": {
            "operator": operator,
            "funders": funders,
            "programme": programme,
            "contest": " ".join(x for x in (programme, raw.get("edition")) if x) or None,
            "project_no": raw.get("projectNumber") or None,
            "grant_date": raw.get("projectGrantDate") or None,
            "competition": raw.get("financedCompetition") == "Tak",
            "total_value": total,
            "national_value": _num(raw.get("nationalFunds")),
            "foreign_value": _num(raw.get("foreignFunds")),
            "grant_value": total,  # RAD-on reports the funds received from the financing institutions
            "currency": "PLN" if total is not None else None,
            "grant_share": None,
            "raw": {"total_value": raw.get("totalFunds")},
        },
        "period": {
            "start": start.isoformat() if start else None,
            "end": end.isoformat() if end else None,
            "precision": "day" if start or end else None,
            "status": status,
            "ongoing": False,
            "raw": f"{raw.get('projectStartDate') or ''} – {raw.get('projectEndDate') or ''}",
        },
        "region": {"voivodeships": voivs, "nationwide": False, "raw": None},
        "keywords": keywords,
        "extra": {
            "category": category,
            "funder_keys": keys,
            "disciplines": disciplines,
            "acronym": raw.get("acronym") or None,
            "partnership": raw.get("partnership") or None,
            "related_projects": raw.get("relatedProjects") or [],
        },
        "rights": {
            "licence": "unknown",
            "llm_may_read_fulltext": True,
            "note": "Otwarte dane RAD-on (OPI PIB, dane z POL-on); warunki ponownego wykorzystania do potwierdzenia.",
        },
        "quality": {
            "status": "needs_review" if blocking else "ok",
            "blocking": blocking,
            "warnings": warnings,
            "narrative_chars": len(abstract),
        },
        "provenance": {
            "connector": f"radar.sources.radon/{CONNECTOR_VERSION}",
            "list_fetched_at": page_fetched_at,
            "detail_fetched_at": page_fetched_at,
            "source_last_refresh": raw.get("lastRefresh"),
            "data_source": raw.get("dataSource"),
            "raw_file": page_file,
        },
    }


# --- raw store + harvest -----------------------------------------------------------
class RawStore:
    """API pages on disk: <root>/<kind>/page-00001.json plus <root>/<kind>.manifest.json listing the
    pages of the latest run, so --offline rebuilds exactly what the last online run saw."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def _manifest(self, kind: str) -> Path:
        return self.root / f"{kind}.manifest.json"

    def put_page(self, kind: str, n: int, resp: Response, token_in: str | None) -> dict:
        path = self.root / kind / f"page-{n:05d}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(resp.text, "utf-8")
        return {"file": f"{kind}/{path.name}", "url": resp.url, "status": resp.status,
                "fetched_at": resp.fetched_at, "token_in": token_in,
                "sha256": hashlib.sha256(resp.text.encode()).hexdigest()}

    def write_manifest(self, kind: str, pages: list[dict], *, complete: bool, max_count: int | None) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        meta = {"kind": kind, "complete": complete, "max_count": max_count, "pages": pages,
                "written_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        tmp = self._manifest(kind).with_suffix(".tmp")
        tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=1), "utf-8")
        tmp.replace(self._manifest(kind))

    def manifest(self, kind: str) -> dict | None:
        p = self._manifest(kind)
        return json.loads(p.read_text("utf-8")) if p.exists() else None

    def read_page(self, entry: dict) -> dict:
        return json.loads((self.root / entry["file"]).read_text("utf-8"))


class FormatChanged(Exception):
    """The API answered with something other than {"results": [...], "pagination": {...}}."""


def _parse(text: str, url: str) -> dict:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise FormatChanged(f"{url}: not JSON ({e})") from e
    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        raise FormatChanged(f"{url}: no 'results' list")
    return data


def iter_pages(store: RawStore, kind: str, base_url: str, *, fetcher: Callable[[str], Response] = fetch_json,
               offline: bool = False, delay: float = 1.0, info: dict | None = None) -> Iterator[tuple[dict, dict]]:
    """Yield (page JSON, manifest entry) for every page. Online: follow tokens, save each page, write the
    manifest at the end (also when the caller stops early; then complete=False)."""
    info = info if info is not None else {}
    if offline:
        manifest = store.manifest(kind)
        if not manifest:
            raise FileNotFoundError(f"brak zapisanych stron '{kind}' w {store.root} (uruchom raz bez --offline)")
        info.update(complete=manifest.get("complete"), max_count=manifest.get("max_count"))
        for entry in manifest["pages"]:
            yield store.read_page(entry), entry
        return
    pages: list[dict] = []
    token: str | None = None
    complete = False
    info.update(complete=False, max_count=None)
    try:
        for n in range(1, 100_000):
            if n > 1 and delay:
                time.sleep(delay)
            url = page_url(base_url, token)
            resp = fetcher(url)
            data = _parse(resp.text, url)
            entry = store.put_page(kind, n, resp, token)
            entry["results"] = len(data["results"])
            pages.append(entry)
            pag = data.get("pagination") or {}
            info["max_count"] = pag.get("maxCount")
            next_token = pag.get("token")
            last = len(data["results"]) < PAGE_SIZE or not next_token or next_token == token
            if last:
                complete = True
                info["complete"] = True
            yield data, entry
            if last:
                break
            token = next_token
    finally:
        store.write_manifest(kind, pages, complete=complete, max_count=info.get("max_count"))


@dataclass
class HarvestStats:
    institutions: int = 0
    pages: int = 0
    projects_seen: int = 0
    max_count: int | None = None
    complete: bool = False
    records: int = 0
    duplicates: int = 0
    skipped_funder: int = 0
    funders: Counter = field(default_factory=Counter)
    status: Counter = field(default_factory=Counter)
    reasons: Counter = field(default_factory=Counter)
    warnings: Counter = field(default_factory=Counter)

    def summary(self) -> str:
        lines = [
            f"institutions in registry: {self.institutions}",
            f"project pages: {self.pages}, projects seen: {self.projects_seen} of {self.max_count}"
            f" ({'complete' if self.complete else 'partial'})",
            f"records: {self.records} (other funders skipped: {self.skipped_funder}, duplicates: {self.duplicates})",
            "funders: " + ", ".join(f"{k}={v}" for k, v in self.funders.most_common()),
            "quality: " + ", ".join(f"{k}={v}" for k, v in self.status.most_common()),
        ]
        if self.reasons:
            lines.append("reasons: " + ", ".join(f"{k}={v}" for k, v in self.reasons.most_common()))
        if self.warnings:
            lines.append("warnings: " + ", ".join(f"{k}={v}" for k, v in self.warnings.most_common()))
        return "\n".join(lines)


def load_institutions(store: RawStore, *, fetcher: Callable[[str], Response] = fetch_json, offline: bool = False,
                      delay: float = 1.0) -> dict[str, dict]:
    raw: list[dict] = []
    for data, _ in iter_pages(store, "institutions", INSTITUTIONS_URL, fetcher=fetcher, offline=offline, delay=delay):
        raw.extend(data["results"])
    return institution_index(raw)


def harvest(store: RawStore, *, fetcher: Callable[[str], Response] = fetch_json,
            funders: tuple[str, ...] | list[str] | None = DEFAULT_FUNDERS,
            institutions: dict[str, dict] | None = None, limit: int | None = None, delay: float = 1.0,
            offline: bool = False, today: date | None = None, stats: HarvestStats | None = None) -> Iterator[dict]:
    """Yield one record per project financed by one of `funders` (None = all funders)."""
    stats = stats if stats is not None else HarvestStats()
    if institutions is None:
        institutions = load_institutions(store, fetcher=fetcher, offline=offline, delay=delay)
    stats.institutions = len(institutions)
    wanted = set(funders) if funders else None
    seen: set[str] = set()
    info: dict = {}
    pages = iter_pages(store, "projects", PROJECTS_URL, fetcher=fetcher, offline=offline, delay=delay, info=info)
    try:
        for data, entry in pages:
            stats.pages += 1
            stats.max_count = info.get("max_count")
            stats.complete = bool(info.get("complete"))
            for raw in data["results"]:
                stats.projects_seen += 1
                keys = funder_keys(raw)
                if wanted is not None and not wanted.intersection(keys):
                    stats.skipped_funder += 1
                    continue
                rec = build_record(raw, institutions, page_fetched_at=entry.get("fetched_at"),
                                   page_file=entry.get("file"), today=today)
                if rec["record_id"] in seen:
                    stats.duplicates += 1
                    continue
                seen.add(rec["record_id"])
                stats.records += 1
                stats.funders[rec["funding"]["operator"] or "?"] += 1
                stats.status[rec["quality"]["status"]] += 1
                for r in rec["quality"]["blocking"]:
                    stats.reasons[r] += 1
                for w in rec["quality"]["warnings"]:
                    stats.warnings[w.split(":")[0]] += 1
                yield rec
                if limit is not None and stats.records >= limit:
                    stats.complete = False
                    return
    finally:
        pages.close()


CSV_COLUMNS = ["record_id", "project_no", "title", "funder", "programme", "leader", "leader_regon",
               "leader_type", "voivodeships", "total_pln", "start", "end", "status", "category", "quality", "reasons"]


def _csv_row(r: dict) -> dict:
    lead = next((o for o in r["organizations"] if o["role"] == "beneficiary"), {})
    return {
        "record_id": r["record_id"], "project_no": r["funding"]["project_no"], "title": r["title"],
        "funder": r["funding"]["operator"], "programme": r["funding"]["programme"], "leader": lead.get("name"),
        "leader_regon": lead.get("regon"), "leader_type": lead.get("kind") or lead.get("type_hint"),
        "voivodeships": ", ".join(r["region"]["voivodeships"]), "total_pln": r["funding"]["total_value"],
        "start": r["period"]["start"], "end": r["period"]["end"], "status": r["period"]["status"],
        "category": r["extra"]["category"], "quality": r["quality"]["status"],
        "reasons": "; ".join(r["quality"]["blocking"] + r["quality"]["warnings"]),
    }


def institutions_path(out: Path) -> Path:
    return out.with_name(out.stem + "_institutions.jsonl")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="data/normalized/radon.jsonl", help="JSONL output (one record per line)")
    ap.add_argument("--institutions-out", default=None,
                    help="institution registry JSONL (default: <out stem>_institutions.jsonl next to --out)")
    ap.add_argument("--csv", default=None, help="optional CSV view for people")
    ap.add_argument("--raw-dir", default="data/raw/radon", help="where raw API pages are saved")
    ap.add_argument("--limit", type=int, default=None, help="stop after N records (partial run)")
    ap.add_argument("--funder", action="append", choices=[*FUNDERS, "all"], default=None,
                    help="keep projects of this funder (repeatable; default: ncn and ncbr; 'all' keeps every funder)")
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between API requests")
    ap.add_argument("--offline", action="store_true", help="use saved raw pages only, no network")
    args = ap.parse_args(argv)

    funders = None if args.funder and "all" in args.funder else tuple(args.funder or DEFAULT_FUNDERS)
    store = RawStore(Path(args.raw_dir))
    stats = HarvestStats()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc)

    institutions = load_institutions(store, offline=args.offline, delay=args.delay)
    inst_out = Path(args.institutions_out) if args.institutions_out else institutions_path(out)
    inst_out.parent.mkdir(parents=True, exist_ok=True)
    tmp = inst_out.with_suffix(inst_out.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for inst in sorted(institutions.values(), key=lambda i: fold(i["name"])):
            fh.write(json.dumps(inst, ensure_ascii=False) + "\n")
    tmp.replace(inst_out)

    tmp = out.with_suffix(out.suffix + ".tmp")
    rows = []
    with tmp.open("w", encoding="utf-8") as fh:
        for rec in harvest(store, funders=funders, institutions=institutions, limit=args.limit, delay=args.delay,
                           offline=args.offline, stats=stats):
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            rows.append(_csv_row(rec))
            if stats.records % 500 == 0:
                print(f"... {stats.records} records ({stats.pages} pages)", file=sys.stderr)
    tmp.replace(out)
    if args.csv:
        Path(args.csv).parent.mkdir(parents=True, exist_ok=True)
        with open(args.csv, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=CSV_COLUMNS, delimiter=";")
            w.writeheader()
            w.writerows(rows)
    secs = (datetime.now(timezone.utc) - started).total_seconds()
    print(stats.summary(), file=sys.stderr)
    print(f"wrote {stats.records} records to {out} and {len(institutions)} institutions to {inst_out} in {secs:.0f}s",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
