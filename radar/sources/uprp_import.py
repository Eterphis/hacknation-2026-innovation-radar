"""UPRP (Polish Patent Office): import of a manual export of search results -> normalized records.

No network access at all. UPRP's e-Wyszukiwarka (ewyszukiwarka.pue.uprp.gov.pl) is behind bot
protection (Incapsula) and the external API (api.uprp.gov.pl) answers 401 without an account issued
by UPRP (see .house/reports/data-access.md). A person exports the result list by hand in the browser
(e.g. search by applicant or by date range, "Eksport" to XLSX or CSV) and saves the file in
`data/import/uprp/`. Every `.xlsx` / `.csv` file there is read; when the same application appears in
several files, the newest file wins.

Columns are matched by name (folded prefixes, Polish or English), so exports with a different column
set or order work: application number, filing date, right (patent) number, publication number and date,
grant date, title, applicants, right holders, inventors, attorney, IPC/CPC, status, kind (patent /
utility model), abstract, address, city, voivodeship, country, link. Required: a title and an
application or right number. Unknown columns are kept in `extra.raw_columns`. Multi-valued cells are
split on `;`, `|` or new lines. CSV: UTF-8 (with or without BOM) or Windows-1250, `;` `,` or tab.

Run:  python -X utf8 -m radar.sources.uprp_import --out data/normalized/uprp.jsonl [--import-dir data/import/uprp]
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
from datetime import date
from pathlib import Path
from typing import Iterator

from .. import RECORD_SCHEMA
from ..pl import parse_voivodeships
from ..text import clean_text, fold
from ..xlsx import excel_date
from .dumps import HeaderMap, file_meta, import_files, read_table, slug
from .ncbr import org_type_hint

SOURCE = "uprp_pl"
SOURCE_NAME = "UPRP – zgłoszenia i patenty krajowe (import ręcznego eksportu z e-Wyszukiwarki)"
CONNECTOR_VERSION = "0.1.0"
CATEGORY = "nauka"
IMPORT_DIR = Path("data/import/uprp")
SEARCH_URL = "https://ewyszukiwarka.pue.uprp.gov.pl/search/simple-search"

# field -> folded header prefixes; more specific first (e.g. "data zgloszenia" before "numer zgloszenia")
ALIASES: list[tuple[str, tuple[str, ...]]] = [
    ("filing_date", ("data zgloszenia", "data dokonania zgloszenia", "filing date", "application date")),
    ("publication_date", ("data publikacji", "data ogloszenia", "publication date")),
    ("grant_date", ("data udzielenia", "data decyzji", "data wydania decyzji", "grant date")),
    ("application_number", ("numer zgloszenia", "nr zgloszenia", "zgloszenie nr", "application number", "application no")),
    ("right_number", ("numer prawa", "nr prawa", "numer patentu", "nr patentu", "patent number", "patent no", "right number")),
    ("publication_number", ("numer publikacji", "nr publikacji", "numer biuletynu", "publication number")),
    ("title", ("tytul", "nazwa wynalazku", "nazwa wzoru", "title")),
    ("applicants", ("zglaszajac", "applicant")),
    ("holders", ("uprawnion", "wlasciciel", "owner", "proprietor", "holder")),
    ("inventors", ("tworc", "wynalazc", "inventor", "autor")),
    ("agent", ("pelnomocnik", "rzecznik", "agent", "representative")),
    ("ipc", ("klasyfikacja", "ipc", "mkp", "cpc", "symbol klas")),
    ("status", ("status", "stan prawny", "stan sprawy", "legal status")),
    ("kind", ("rodzaj", "typ ochrony", "przedmiot ochrony", "typ", "kind")),
    ("abstract", ("streszczenie", "abstrakt", "abstract", "opis")),
    ("url", ("link", "url", "adres www", "odnosnik")),
    ("address", ("adres", "address")),
    ("city", ("miejscowosc", "miasto", "city")),
    ("voivodeship", ("wojewodztwo", "region")),
    ("country", ("kraj", "country")),
    ("lp", ("lp", "l.p", "no.")),
]
REQUIRED = [("title", "application_number"), ("title", "right_number")]
LEGAL_FORMS = ("sp. z o.o", "spolka", "s.a.", " sa ", "sp.k", "sp. j", "s.c.", "fundacja", "stowarzyszenie",
               "uniwersytet", "politechnika", "akademia", "instytut", "uczelnia", "centrum", "szpital", "przedsiebiorstwo",
               "zaklad", "gmina", "miasto", "skarb panstwa", "siec ", "osrodek", "laboratorium", "gmbh", " ltd",
               " inc", " ag", " oy", " ab", " s.r.l", " llc", " co.", "corporation", "company", "group", "przemysl")


class FormatChanged(Exception):
    """No header row with a title and an application/right number."""


# --- parsing helpers ---------------------------------------------------------------
def split_multi(value: str | None) -> list[str]:
    if not value:
        return []
    parts = re.split(r"\s*(?:;|\||\n)\s*", value)
    return list(dict.fromkeys(clean_text(p) for p in parts if clean_text(p)))


def parse_date(value: str | None) -> date | None:
    """'2023-05-17', '17.05.2023', '17-05-2023', '2023.05.17' or an Excel serial day."""
    v = (value or "").strip()
    if not v:
        return None
    if re.fullmatch(r"\d+(\.0+)?", v):
        return excel_date(v)
    m = re.match(r"(\d{4})[-./](\d{1,2})[-./](\d{1,2})", v)
    if m:
        y, mo, d = map(int, m.groups())
    else:
        m = re.match(r"(\d{1,2})[-./](\d{1,2})[-./](\d{4})", v)
        if not m:
            return None
        d, mo, y = map(int, m.groups())
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def normalize_number(value: str | None) -> str | None:
    """'P.444 555', 'P-444555', 'W.130000' -> 'P.444555' / 'W.130000'; bare digits kept."""
    v = re.sub(r"\s+", "", value or "").upper()
    if not v:
        return None
    m = re.fullmatch(r"(PL)?([PWUR])[.\-]?(\d+)", v)
    return f"{m.group(2)}.{m.group(3)}" if m else v


def is_organization(name: str) -> bool:
    f = " " + fold(name) + " "
    if org_type_hint(name) or any(w in f for w in LEGAL_FORMS) or re.search(r"\d", name):
        return True
    words = re.findall(r"[^\W\d_]+", name)
    return not (2 <= len(words) <= 4)  # "Jan Kowalski", "KOWALSKI JAN MARIA" -> person


def strip_location(party: str) -> tuple[str, str | None, str | None]:
    """'POLITECHNIKA RZESZOWSKA, Rzeszów, PL' -> ('POLITECHNIKA RZESZOWSKA', 'Rzeszów', 'PL')."""
    m = re.match(r"(.+?),\s*([^,]+?)\s*,\s*([A-Z]{2})\s*$", party)
    if m:
        return clean_text(m.group(1)), clean_text(m.group(2)), m.group(3)
    m = re.match(r"(.+?)\s*\(([A-Z]{2})\)\s*$", party)
    if m:
        return clean_text(m.group(1)), None, m.group(2)
    return party, None, None


def kind_of(row: dict) -> str:
    f = fold(" ".join(row.get(k, "") for k in ("kind", "application_number", "right_number")))
    if "wzor uzytkow" in f or "utility" in f or re.search(r"(^|\s|pl)w[.\-]?\d", f):
        return "utility_model"
    if "wzor przemysl" in f or "design" in f:
        return "industrial_design"
    return "patent"


def status_of(row: dict, grant: date | None) -> str:
    f = fold(row.get("status", ""))
    if grant or any(w in f for w in ("udzielon", "w mocy", "granted", "in force")):
        return "granted"
    if any(w in f for w in ("wygas", "umorz", "odmow", "cofni", "uniewaznion", "lapsed", "refused", "withdrawn")):
        return "ended"
    return "pending_or_unknown"


# --- normalization -------------------------------------------------------------------
def build_record(row: dict[str, str], *, file_row: int, file: dict, raw_columns: dict | None = None) -> dict:
    title = row.get("title", "")
    app_no = normalize_number(row.get("application_number"))
    right_no = normalize_number(row.get("right_number"))
    filed, published, granted_on = (parse_date(row.get(k)) for k in ("filing_date", "publication_date", "grant_date"))
    kind = kind_of(row)
    status = status_of(row, granted_on)
    abstract = row.get("abstract") or None
    ipc = split_multi(row.get("ipc"))
    region_voivs, _ = parse_voivodeships(row.get("voivodeship") or row.get("address"))

    orgs, people = [], []
    for role, key in (("applicant", "applicants"), ("right_holder", "holders")):
        for party in split_multi(row.get(key)):
            name, city, cc = strip_location(party)
            if any(fold(o["name"]) == fold(name) for o in orgs) or any(fold(p["name"]) == fold(name) for p in people):
                continue
            if is_organization(name):
                orgs.append({"name": name, "role": role, "country": cc or row.get("country") or None,
                             "type_hint": org_type_hint(name),
                             "location": {"city": city or row.get("city") or None, "address": row.get("address") or None,
                                          "country": cc or row.get("country") or None},
                             "org_id": None, "is_public": None, "source_text": party})
            else:
                people.append({"name": name, "role": role, "country": cc, "source_text": party})
    for party in split_multi(row.get("inventors")):
        name, _, cc = strip_location(party)
        people.append({"name": name, "role": "inventor", "country": cc, "source_text": party})

    number_key = app_no or right_no
    record_id = "pl-" + slug(number_key) if number_key else f"row-{hashlib.sha1(json.dumps(row, sort_keys=True).encode()).hexdigest()[:12]}"
    text_for_llm = "\n\n".join(x for x in [
        f"Tytuł: {title}",
        f"Streszczenie:\n{abstract}" if abstract else "",
        f"Klasy IPC: {', '.join(ipc)}" if ipc else "",
        "Zgłaszający: " + "; ".join(o["name"] for o in orgs) if orgs else "",
    ] if x)

    blocking, warnings = [], []
    if not title:
        blocking.append("missing_title")
    if not number_key:
        blocking.append("missing_number")
    if not abstract:
        warnings.append("no_abstract_in_export")
    if row.get("filing_date") and not filed:
        warnings.append("filing_date_unparsed")
    if not orgs and not any(p["role"] in ("applicant", "right_holder") for p in people):
        warnings.append("no_applicant")

    content = {k: v for k, v in sorted(row.items()) if k != "lp"}
    return {
        "schema": RECORD_SCHEMA,
        "source": SOURCE,
        "source_name": SOURCE_NAME,
        "record_id": record_id,
        "url": row.get("url") or None,
        "list_url": SEARCH_URL,
        "content_hash": hashlib.sha256(json.dumps(content, ensure_ascii=False).encode()).hexdigest(),
        "record_type": "utility_model_application" if kind == "utility_model" else "patent_application",
        "language": "pl",
        "title": title,
        "intro": None,
        "text": {"abstract": abstract, "first_claim": None, "description": None, "other": []},
        "text_for_llm": text_for_llm,
        "organizations": orgs,
        "people": people,
        "funding": {},
        "patent": {
            "office": "UPRP",
            "kind": kind,
            "application_number": app_no,
            "right_number": right_no,
            "publication_number": row.get("publication_number") or None,
            "filing_date": filed.isoformat() if filed else None,
            "publication_date": published.isoformat() if published else None,
            "grant_date": granted_on.isoformat() if granted_on else None,
            "granted": status == "granted",
            "status_raw": row.get("status") or None,
            "agent": row.get("agent") or None,
            "ipc": ipc,
            "cpc": [],
        },
        "period": {"start": filed.isoformat() if filed else None, "end": None, "precision": "day" if filed else None,
                   "status": status, "ongoing": False,
                   "raw": f"zgłoszenie {row.get('filing_date') or '?'}" + (f", udzielenie {row['grant_date']}" if row.get("grant_date") else "")},
        "region": {"voivodeships": region_voivs, "nationwide": False,
                   "raw": row.get("voivodeship") or row.get("city") or None, "country": row.get("country") or "PL"},
        "keywords": [],
        "extra": {"category": CATEGORY, "raw_columns": raw_columns or {}},
        "rights": {"licence": "dane publiczne UPRP (rejestr)", "llm_may_read_fulltext": True,
                   "note": "Ręczny eksport wyników z e-Wyszukiwarki UPRP; automatyczne pobieranie jest zablokowane."},
        "quality": {"status": "needs_review" if blocking else "ok", "blocking": blocking, "warnings": warnings,
                    "narrative_chars": len(abstract or "")},
        "provenance": {
            "connector": f"radar.sources.uprp_import/{CONNECTOR_VERSION}",
            "list_fetched_at": file.get("fetched_at"),
            "detail_fetched_at": file.get("fetched_at"),
            "source_file": Path(file["path"]).name,
            "source_file_sha256": file.get("sha256"),
            "source_row": file_row,
            "raw_files": {"source_file": file["path"]},
        },
    }


# --- raw store + harvest -------------------------------------------------------------
class RawStore:
    """Manifest of the imported files (name, size, SHA-256, rows) in `<raw-dir>/import.meta.json`."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def save_manifest(self, files: list[dict]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "import.meta.json").write_text(json.dumps({"files": files}, ensure_ascii=False, indent=1), "utf-8")


@dataclass
class HarvestStats:
    files: list = field(default_factory=list)
    rows: int = 0
    records: int = 0
    duplicates: int = 0
    status: Counter = field(default_factory=Counter)
    reasons: Counter = field(default_factory=Counter)
    kinds: Counter = field(default_factory=Counter)

    def summary(self) -> str:
        lines = [f"file: {f['path']} ({f.get('rows', 0)} rows, columns: {', '.join(f.get('columns', []))})" for f in self.files]
        lines.append(f"rows: {self.rows}, records: {self.records} (duplicates skipped: {self.duplicates})")
        lines.append("kinds: " + ", ".join(f"{k}={v}" for k, v in self.kinds.most_common()))
        lines.append("quality: " + ", ".join(f"{k}={v}" for k, v in self.status.most_common()))
        if self.reasons:
            lines.append("reasons: " + ", ".join(f"{k}={v}" for k, v in self.reasons.most_common()))
        return "\n".join(lines)


def harvest(store: RawStore | None, *, files: list[Path] | None = None, import_dir: Path = IMPORT_DIR,
            limit: int | None = None, stats: HarvestStats | None = None) -> Iterator[dict]:
    stats = stats if stats is not None else HarvestStats()
    paths = files if files is not None else import_files(import_dir)
    if not paths:
        raise FileNotFoundError(f"brak plików .xlsx/.csv w {import_dir} (zapisz tam ręczny eksport z e-Wyszukiwarki UPRP)")
    seen: set[str] = set()
    for path in paths:  # newest first: the first occurrence of an application wins
        meta = file_meta(path)
        rows = read_table(path)
        header = HeaderMap.find(rows, ALIASES, REQUIRED)
        if header is None:
            raise FormatChanged(f"{path}: nie znaleziono nagłówka z tytułem i numerem zgłoszenia/prawa")
        known = set(header.columns.values())
        head_row = rows[header.header_row]
        extra_cols = {i: clean_text(h) for i, h in enumerate(head_row) if i not in known and clean_text(h)}
        data = header.records(rows)
        meta.update(rows=len(data), columns=sorted(header.columns))
        stats.files.append(meta)
        stats.rows += len(data)
        for file_row, values in data:
            raw_row = rows[file_row - 1]
            raw_columns = {name: clean_text(raw_row[i]) for i, name in extra_cols.items() if i < len(raw_row) and clean_text(raw_row[i])}
            rec = build_record(values, file_row=file_row, file=meta, raw_columns=raw_columns)
            if rec["record_id"] in seen:
                stats.duplicates += 1
                continue
            if limit is not None and stats.records >= limit:
                break
            seen.add(rec["record_id"])
            stats.records += 1
            stats.kinds[rec["patent"]["kind"]] += 1
            stats.status[rec["quality"]["status"]] += 1
            for r in rec["quality"]["blocking"]:
                stats.reasons[r] += 1
            yield rec
    if store is not None:
        store.save_manifest(stats.files)


CSV_COLUMNS = ["record_id", "title", "kind", "application_number", "right_number", "filing_date", "status",
               "applicants", "inventors", "ipc", "has_abstract", "quality"]


def _csv_row(r: dict) -> dict:
    p = r["patent"]
    return {"record_id": r["record_id"], "title": r["title"], "kind": p["kind"],
            "application_number": p["application_number"], "right_number": p["right_number"],
            "filing_date": p["filing_date"], "status": r["period"]["status"],
            "applicants": "; ".join(o["name"] for o in r["organizations"]),
            "inventors": "; ".join(x["name"] for x in r["people"] if x["role"] == "inventor"),
            "ipc": ", ".join(p["ipc"][:5]), "has_abstract": bool(r["text"]["abstract"]), "quality": r["quality"]["status"]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="data/normalized/uprp.jsonl")
    ap.add_argument("--csv", default=None)
    ap.add_argument("--raw-dir", default="data/raw/uprp", help="where the import manifest is written")
    ap.add_argument("--import-dir", default=str(IMPORT_DIR), help="folder with exported .xlsx/.csv files")
    ap.add_argument("--file", action="append", default=None, help="import only this file (repeatable)")
    ap.add_argument("--offline", action="store_true", help="accepted for a uniform interface; this connector never uses the network")
    ap.add_argument("--limit", type=int, default=None, help="stop after N records")
    args = ap.parse_args(argv)

    stats = HarvestStats()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    rows = []
    files = [Path(f) for f in args.file] if args.file else None
    with tmp.open("w", encoding="utf-8") as fh:
        for rec in harvest(RawStore(Path(args.raw_dir)), files=files, import_dir=Path(args.import_dir),
                           limit=args.limit, stats=stats):
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
