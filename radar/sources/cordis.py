"""CORDIS: EU research projects (Horizon Europe 2021–2027 and Horizon 2020) with a Polish participant.

Source: the open CORDIS dumps listed on the EU open data portal (data.europa.eu, datasets
`cordis-eu-research-projects-under-horizon-europe-2021-2027` and `cordish2020projects`, licence CC BY 4.0):

    https://cordis.europa.eu/data/cordis-HORIZONprojects-csv.zip   (~38 MB, ~24k projects)
    https://cordis.europa.eu/data/cordis-h2020projects-csv.zip     (~55 MB, ~35k projects)

The file names are stable (the files are replaced in place, roughly monthly; `Last-Modified` and `ETag`
are sent), so a run costs one conditional request per programme when nothing changed. Each ZIP holds
`project.csv` (id, acronym, title, objective, dates, costs, scheme, keywords, DOI) and `organization.csv`
(one row per participation: name, VAT, SME, activity type, address, NUTS, role, EU contribution), both
`;`-separated UTF-8. A project becomes a record when at least one participant has `country = PL`;
all participants are kept, Polish ones flagged and mapped to a voivodeship by NUTS-2 code.

`cordis.europa.eu/robots.txt` disallows `/data/` for crawlers. This connector does not crawl: it
downloads two files the publisher lists as the official distribution of an open dataset, at most once
per refresh and only when they changed (conditional GET). The page per project
(`https://cordis.europa.eu/project/id/<id>`) is only linked, never fetched.

Run:  python -X utf8 -m radar.sources.cordis --out data/normalized/cordis.jsonl [--programme HORIZON]
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sys
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable, Iterator

from .. import RECORD_SCHEMA
from ..text import clean_text
from .dumps import download_if_changed, num, saved_file
from .ncbr import org_type_hint

SOURCE = "cordis_pl"
SOURCE_NAME = "CORDIS – projekty Horizon Europe i Horizon 2020 z udziałem organizacji z Polski"
CONNECTOR_VERSION = "0.1.0"
CATEGORY = "projekty"
PROJECT_URL = "https://cordis.europa.eu/project/id/{id}"
DUMPS = {
    "HORIZON": "https://cordis.europa.eu/data/cordis-HORIZONprojects-csv.zip",
    "H2020": "https://cordis.europa.eu/data/cordis-h2020projects-csv.zip",
}
PROGRAMME_NAMES = {"HORIZON": "Horizon Europe (2021–2027)", "H2020": "Horizon 2020 (2014–2020)"}
MIN_TEXT_CHARS = 200

# NUTS-2 (2021) -> voivodeship
NUTS2_PL = {
    "PL21": "małopolskie", "PL22": "śląskie", "PL41": "wielkopolskie", "PL42": "zachodniopomorskie",
    "PL43": "lubuskie", "PL51": "dolnośląskie", "PL52": "opolskie", "PL61": "kujawsko-pomorskie",
    "PL62": "warmińsko-mazurskie", "PL63": "pomorskie", "PL71": "łódzkie", "PL72": "świętokrzyskie",
    "PL81": "lubelskie", "PL82": "podkarpackie", "PL84": "podlaskie", "PL91": "mazowieckie",
    "PL92": "mazowieckie", "PL12": "mazowieckie", "PL11": "łódzkie", "PL31": "lubelskie", "PL32": "podkarpackie",
    "PL33": "świętokrzyskie", "PL34": "podlaskie",  # NUTS 2013/2016 codes still found in older rows
}
ACTIVITY = {"HES": "university", "REC": "research_institute", "PRC": "company", "PUB": "public_body", "OTH": "other"}
STATUS = {"SIGNED": None, "CLOSED": "finished", "TERMINATED": "terminated"}


class FormatChanged(Exception):
    """The dump no longer has the files or columns this connector expects."""


# --- reading the ZIP ------------------------------------------------------------------
def _csv(z: zipfile.ZipFile, name: str) -> Iterator[dict[str, str]]:
    member = next((n for n in z.namelist() if n.rsplit("/", 1)[-1] == name), None)
    if member is None:
        raise FormatChanged(f"w archiwum nie ma pliku {name}")
    with z.open(member) as fh:
        # a few rows carry more fields than the header (stray `;`); keep them under "_rest", not under None
        yield from csv.DictReader(io.TextIOWrapper(fh, "utf-8-sig", newline=""), delimiter=";", restkey="_rest")


PROJECT_COLUMNS = ("id", "acronym", "title", "objective", "startDate", "endDate")
ORG_COLUMNS = ("projectID", "name", "country", "role")


def read_dump(data: bytes | Path, country: str = "PL") -> tuple[list[dict], dict[str, list[dict]]]:
    """(projects with a participant from `country`, {project id: [organization rows]})."""
    z = zipfile.ZipFile(data if isinstance(data, Path) else io.BytesIO(data))
    orgs: dict[str, list[dict]] = defaultdict(list)
    first = True
    for row in _csv(z, "organization.csv"):
        if first:
            missing = [c for c in ORG_COLUMNS if c not in row]
            if missing:
                raise FormatChanged("organization.csv bez kolumn: " + ", ".join(missing))
            first = False
        orgs[row["projectID"]].append(row)
    wanted = {pid for pid, rows in orgs.items() if any(r.get("country") == country for r in rows)}
    projects = []
    first = True
    for row in _csv(z, "project.csv"):
        if first:
            missing = [c for c in PROJECT_COLUMNS if c not in row]
            if missing:
                raise FormatChanged("project.csv bez kolumn: " + ", ".join(missing))
            first = False
        if row["id"] in wanted:
            projects.append(row)
    return projects, {pid: orgs[pid] for pid in wanted}


# --- normalization -------------------------------------------------------------------
def _date(value: str | None) -> date | None:
    try:
        return date.fromisoformat((value or "")[:10])
    except ValueError:
        return None


def _bool(value: str | None) -> bool | None:
    v = (value or "").strip().lower()
    return True if v == "true" else False if v == "false" else None


def _org(row: dict, country: str) -> dict:
    nuts = (row.get("nutsCode") or "").strip()
    name = clean_text(row.get("name", ""))
    activity = (row.get("activityType") or "").strip()
    return {
        "name": name,
        "short_name": clean_text(row.get("shortName", "")) or None,
        "role": (row.get("role") or "participant").strip() or "participant",
        "country": row.get("country") or None,
        "is_target_country": row.get("country") == country,
        "type_hint": ACTIVITY.get(activity) or org_type_hint(name),
        "activity_type": activity or None,
        "sme": _bool(row.get("SME")),
        "org_id": row.get("organisationID") or None,
        "vat": row.get("vatNumber") or None,
        "is_public": True if activity == "PUB" else None,
        "url": row.get("organizationURL") or None,
        "location": {"street": clean_text(row.get("street", "")) or None, "postal_code": row.get("postCode") or None,
                     "city": clean_text(row.get("city", "")) or None, "country": row.get("country") or None,
                     "nuts": nuts or None, "voivodeship": NUTS2_PL.get(nuts[:4]) if nuts.startswith("PL") else None},
        "ec_contribution": num(row.get("ecContribution")),
        "order": int(row["order"]) if (row.get("order") or "").isdigit() else None,
    }


def build_record(p: dict, org_rows: list[dict], *, programme: str, country: str, file_meta: dict,
                 today: date | None = None) -> dict:
    today = today or date.today()
    title, objective = clean_text(p.get("title", "")), clean_text(p.get("objective", ""))
    start, end = _date(p.get("startDate")), _date(p.get("endDate"))
    status = STATUS.get((p.get("status") or "").upper())
    if status is None:
        if end and end < today:
            status = "finished"
        elif start and start > today:
            status = "planned"
        elif start:
            status = "running"
    orgs = sorted((_org(r, country) for r in org_rows), key=lambda o: (o["role"] != "coordinator", o["order"] or 999))
    local = [o for o in orgs if o["is_target_country"]]
    voivs = list(dict.fromkeys(o["location"]["voivodeship"] for o in local if o["location"]["voivodeship"]))
    keywords = [k.strip() for k in (p.get("keywords") or "").replace(";", ",").split(",") if k.strip()]
    total, ec = num(p.get("totalCost")), num(p.get("ecMaxContribution"))
    pl_ec = round(sum(o["ec_contribution"] or 0 for o in local), 2) if local else None

    text_for_llm = "\n\n".join(x for x in [
        f"Tytuł: {title}" + (f" ({p['acronym']})" if p.get("acronym") else ""),
        f"Cel projektu:\n{objective}" if objective else "",
        f"Słowa kluczowe: {', '.join(keywords)}" if keywords else "",
        "Uczestnicy z Polski: " + "; ".join(o["name"] for o in local) if local else "",
    ] if x)

    blocking, warnings = [], []
    if not title:
        blocking.append("missing_title")
    if len(objective) < MIN_TEXT_CHARS:
        blocking.append("short_text")
    if local and not voivs:
        warnings.append("region_unparsed")
    if (p.get("startDate") and not start) or (p.get("endDate") and not end):
        warnings.append("period_unparsed")

    content = {"project": p, "organizations": org_rows}
    pid = p["id"]
    return {
        "schema": RECORD_SCHEMA,
        "source": SOURCE,
        "source_name": SOURCE_NAME,
        "record_id": f"{programme.lower()}-{pid}",
        "url": PROJECT_URL.format(id=pid),
        "list_url": DUMPS[programme] if programme in DUMPS else None,
        "content_hash": hashlib.sha256(json.dumps(content, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
        "record_type": "eu_research_project",
        "language": "en",
        "title": title,
        "intro": None,
        "text": {"description": objective or None, "other": []},
        "text_for_llm": text_for_llm,
        "organizations": orgs,
        "people": [],
        "funding": {
            "operator": "Komisja Europejska",
            "programme": PROGRAMME_NAMES.get(programme, programme),
            "framework_programme": p.get("frameworkProgramme") or programme,
            "contest": p.get("masterCall") or None,
            "sub_call": p.get("subCall") or None,
            "topics": p.get("topics") or None,
            "funding_scheme": p.get("fundingScheme") or None,
            "legal_basis": p.get("legalBasis") or None,
            "project_no": pid,
            "acronym": p.get("acronym") or None,
            "doi": p.get("grantDoi") or None,
            "total_value": total,
            "grant_value": ec,
            "grant_value_computed": False,
            "grant_value_target_country": pl_ec,
            "currency": "EUR",
            "grant_share": round(ec / total, 4) if total and ec is not None else None,
            "raw": {"total_value": p.get("totalCost") or None, "grant_value": p.get("ecMaxContribution") or None},
        },
        "period": {
            "start": start.isoformat() if start else None,
            "end": end.isoformat() if end else None,
            "precision": "day" if start or end else None,
            "status": status,
            "ongoing": False,
            "raw": f"{p.get('startDate', '')} – {p.get('endDate', '')}",
        },
        "region": {"voivodeships": voivs, "nationwide": False,
                   "raw": ", ".join(dict.fromkeys(o["location"]["city"] for o in local if o["location"]["city"])) or None,
                   "country": country},
        "keywords": keywords,
        "extra": {"category": CATEGORY, "cordis_status": p.get("status") or None,
                  "signature_date": p.get("ecSignatureDate") or None, "rcn": p.get("rcn") or None,
                  "content_updated": p.get("contentUpdateDate") or None,
                  "participants": len(orgs), "participants_target_country": len(local)},
        "rights": {"licence": "CC BY 4.0",
                   "llm_may_read_fulltext": True,
                   "note": "CORDIS, © Unia Europejska; dane otwarte na licencji CC BY 4.0 (data.europa.eu)."},
        "quality": {"status": "needs_review" if blocking else "ok", "blocking": blocking, "warnings": warnings,
                    "narrative_chars": len(objective)},
        "provenance": {
            "connector": f"radar.sources.cordis/{CONNECTOR_VERSION}",
            "list_fetched_at": file_meta.get("fetched_at"),
            "detail_fetched_at": file_meta.get("fetched_at"),
            "source_file_url": file_meta.get("url"),
            "source_file_last_modified": file_meta.get("last_modified"),
            "raw_files": {"source_file": file_meta.get("path")},
        },
    }


# --- raw store + harvest -------------------------------------------------------------
class RawStore:
    """One ZIP per programme (`<programme>-projects-csv.zip`) plus its meta file (ETag, Last-Modified)."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def path(self, programme: str) -> Path:
        return self.root / f"cordis-{programme}projects-csv.zip"


@dataclass
class HarvestStats:
    files: dict = field(default_factory=dict)
    projects: int = 0
    records: int = 0
    status: Counter = field(default_factory=Counter)
    reasons: Counter = field(default_factory=Counter)
    voivodeships: Counter = field(default_factory=Counter)

    def summary(self) -> str:
        lines = [f"{p}: {m.get('url')} ({'pobrany' if m.get('changed') else 'bez zmian / z dysku'}, "
                 f"{m.get('bytes')} B, Last-Modified {m.get('last_modified')}), projekty z PL: {m.get('projects')}"
                 for p, m in self.files.items()]
        lines.append(f"records: {self.records}")
        lines.append("quality: " + ", ".join(f"{k}={v}" for k, v in self.status.most_common()))
        if self.reasons:
            lines.append("reasons: " + ", ".join(f"{k}={v}" for k, v in self.reasons.most_common()))
        lines.append("voivodeships: " + ", ".join(f"{k}={v}" for k, v in self.voivodeships.most_common(6)))
        return "\n".join(lines)


def harvest(store: RawStore, *, programmes: tuple[str, ...] = ("HORIZON", "H2020"), country: str = "PL",
            offline: bool = False, force: bool = False, limit: int | None = None, today: date | None = None,
            downloader: Callable[..., dict] = download_if_changed, stats: HarvestStats | None = None) -> Iterator[dict]:
    stats = stats if stats is not None else HarvestStats()
    for programme in programmes:
        dest = store.path(programme)
        if offline:
            meta = saved_file(dest)
            if not meta:
                raise FileNotFoundError(f"brak zapisanego zrzutu {dest} (uruchom raz bez --offline)")
        else:
            meta = downloader(DUMPS[programme], dest, expect_zip=True, force=force)
        projects, orgs = read_dump(Path(meta["path"]), country)
        projects.sort(key=lambda p: (p.get("startDate") or "", p["id"]), reverse=True)  # newest first for --limit
        stats.files[programme] = {**meta, "projects": len(projects)}
        for p in projects:
            if limit is not None and stats.records >= limit:
                return
            rec = build_record(p, orgs.get(p["id"], []), programme=programme, country=country, file_meta=meta, today=today)
            stats.projects += 1
            stats.records += 1
            stats.status[rec["quality"]["status"]] += 1
            for r in rec["quality"]["blocking"]:
                stats.reasons[r] += 1
            for v in rec["region"]["voivodeships"]:
                stats.voivodeships[v] += 1
            yield rec


CSV_COLUMNS = ["record_id", "acronym", "title", "programme", "scheme", "coordinator", "pl_participants",
               "voivodeships", "total_eur", "ec_eur", "pl_ec_eur", "start", "end", "status", "quality", "url"]


def _csv_row(r: dict) -> dict:
    f = r["funding"]
    coord = next((o["name"] for o in r["organizations"] if o["role"] == "coordinator"), None)
    return {"record_id": r["record_id"], "acronym": f["acronym"], "title": r["title"], "programme": f["programme"],
            "scheme": f["funding_scheme"], "coordinator": coord,
            "pl_participants": "; ".join(o["name"] for o in r["organizations"] if o["is_target_country"]),
            "voivodeships": ", ".join(r["region"]["voivodeships"]), "total_eur": f["total_value"],
            "ec_eur": f["grant_value"], "pl_ec_eur": f["grant_value_target_country"], "start": r["period"]["start"],
            "end": r["period"]["end"], "status": r["period"]["status"], "quality": r["quality"]["status"], "url": r["url"]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="data/normalized/cordis.jsonl")
    ap.add_argument("--csv", default=None)
    ap.add_argument("--raw-dir", default="data/raw/cordis")
    ap.add_argument("--offline", action="store_true", help="use the saved dumps only, no network")
    ap.add_argument("--force", action="store_true", help="download even if the server reports no change")
    ap.add_argument("--limit", type=int, default=None, help="stop after N records (newest projects first)")
    ap.add_argument("--programme", action="append", choices=sorted(DUMPS), default=None,
                    help="HORIZON and/or H2020 (default: both)")
    ap.add_argument("--country", default="PL", help="participant country code (default PL)")
    args = ap.parse_args(argv)

    stats = HarvestStats()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    rows = []
    with tmp.open("w", encoding="utf-8") as fh:
        for rec in harvest(RawStore(Path(args.raw_dir)), programmes=tuple(args.programme or ("HORIZON", "H2020")),
                           country=args.country, offline=args.offline, force=args.force, limit=args.limit, stats=stats):
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            rows.append(_csv_row(rec))
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
