"""Interreg 2021–2027 project list (interreg.gov.pl) -> normalized records.

The page https://interreg.gov.pl/lista-projektow/ links one XLSX ("Wykaz projektów … art. 49 CPR"),
published by the managing authority and replaced when updated; its file name carries a date, so the
link is read from the page on every run. One row = one project = one record.

Run:  python -X utf8 -m radar.sources.interreg --out data/normalized/interreg.jsonl
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
from typing import Callable, Iterator
from urllib.parse import urljoin

from .. import RECORD_SCHEMA
from ..http import BinaryResponse, Response, fetch, fetch_bytes
from ..pl import parse_voivodeships
from ..text import clean_text, fold
from ..xlsx import excel_date, read_rows
from .ncbr import org_type_hint

SOURCE = "interreg_pl"
SOURCE_NAME = "Interreg 2021–2027 – wykaz projektów (interreg.gov.pl)"
CONNECTOR_VERSION = "0.1.0"
LIST_URL = "https://interreg.gov.pl/lista-projektow/"
MIN_TEXT_CHARS = 200
DESCRIPTION_LIMIT = 4000  # the published file cuts descriptions at 4000 characters

# Column header prefix (folded) -> field. Order matters: the longer "partners" header goes first.
HEADERS: list[tuple[str, str]] = [
    ("programme", "program"),
    ("project_no", "numer projektu"),
    ("title", "tytul projektu"),
    ("description", "opis projektu"),
    ("start", "data rozpoczecia"),
    ("end", "data zakonczenia"),
    ("total", "wydatki"),  # the file spells it "Wydatki 0gółem" (digit zero)
    ("eu_rate", "stopa dofinansowania"),
    ("fund", "fundusz"),
    ("objective", "cel szczegolowy"),
    ("partners", "nazwa partnera wiodacego i partnerow"),
    ("lead", "nazwa partnera wiodacego"),
    ("postal_code", "kod pocztowy"),
    ("country", "kraj"),
    ("region", "wojewodztwo lub region"),
    ("powiat", "powiat"),
    ("gmina", "gmina"),
    ("city", "miejscowosc"),
    ("intervention", "zakres interwencji"),
    ("strategic", "projekt strategiczny"),
    ("above_5m", "projekt powyzej 5 mln"),
]
REQUIRED = ("project_no", "title", "description", "lead")


class FormatChanged(Exception):
    """The spreadsheet no longer has the columns this connector expects."""


# --- page and spreadsheet ----------------------------------------------------
def find_xlsx_link(html: str, base: str = LIST_URL) -> str | None:
    links = re.findall(r'href="([^"]+\.xlsx)"', html, re.I)
    preferred = [u for u in links if re.search(r"wykaz|projekt", u, re.I)]
    chosen = (preferred or links or [None])[0]
    return urljoin(base, chosen) if chosen else None


def map_header(row: list[str]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for idx, cell in enumerate(row):
        f = fold(cell)
        for key, prefix in HEADERS:
            if key not in mapping and f.startswith(prefix):
                mapping[key] = idx
                break
    return mapping


def parse_sheet(rows: list[list[str]]) -> tuple[dict[str, int], list[tuple[int, dict[str, str]]]]:
    """Find the header row, return (column map, [(excel_row_number, {field: value})])."""
    for i, row in enumerate(rows[:20]):
        mapping = map_header(row)
        if all(k in mapping for k in REQUIRED):
            break
    else:
        raise FormatChanged("nie znaleziono wiersza nagłówków z kolumnami: " + ", ".join(REQUIRED))
    out = []
    for j, row in enumerate(rows[i + 1:], start=i + 2):
        values = {k: clean_text(row[c]) if c < len(row) else "" for k, c in mapping.items()}
        if any(values.values()):
            out.append((j, values))
    return mapping, out


# --- normalization -------------------------------------------------------------
def _num(value: str) -> float | None:
    try:
        return round(float(value.replace(" ", "").replace(",", ".")), 2)
    except (ValueError, AttributeError):
        return None


def _flag(value: str) -> bool | None:
    f = fold(value)
    return True if f in ("t", "tak", "y", "yes") else False if f in ("n", "nie", "no") else None


def record_id(project_no: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", fold(project_no)).strip("-")


def split_partners(raw: str) -> list[str]:
    return list(dict.fromkeys(p.strip() for p in raw.split("|") if p.strip()))


def build_record(row: dict[str, str], *, excel_row: int, file_url: str | None, list_fetched_at: str | None,
                 file_fetched_at: str | None, raw_files: dict | None = None, today: date | None = None) -> dict:
    today = today or date.today()
    title, desc, number = row.get("title", ""), row.get("description", ""), row.get("project_no", "")
    start, end = excel_date(row.get("start")), excel_date(row.get("end"))
    status = None
    if end and end < today:
        status = "finished"
    elif start and start > today:
        status = "planned"
    elif start:
        status = "running"

    lead = row.get("lead", "")
    partners = split_partners(row.get("partners", ""))
    location = {k: row.get(k) or None for k in ("postal_code", "city", "gmina", "powiat", "region", "country")}
    orgs = []
    if lead:
        orgs.append({"name": lead, "role": "lead_partner", "type_hint": org_type_hint(lead), "location": location,
                     "org_id": None, "is_public": None})
    for p in partners:
        if fold(p) != fold(lead):
            orgs.append({"name": p, "role": "partner", "type_hint": org_type_hint(p), "org_id": None, "is_public": None})

    total = _num(row.get("total", ""))
    rate = _num(row.get("eu_rate", ""))
    grant = round(total * rate / 100, 2) if total is not None and rate is not None else None
    voivs, _ = parse_voivodeships(row.get("region")) if fold(row.get("country", "")) == "polska" else ([], False)

    text_for_llm = "\n\n".join(x for x in [
        f"Tytuł: {title}",
        f"Opis projektu:\n{desc}" if desc else "",
        f"Cel szczegółowy: {row['objective']}" if row.get("objective") else "",
        f"Zakres interwencji: {row['intervention']}" if row.get("intervention") else "",
    ] if x)

    blocking, warnings = [], []
    if not title:
        blocking.append("missing_title")
    if not number:
        blocking.append("missing_project_no")
    if len(desc) < MIN_TEXT_CHARS:
        blocking.append("short_text")
    if len(desc) >= DESCRIPTION_LIMIT:
        warnings.append("description_truncated_in_source")
    if row.get("start") and not start or row.get("end") and not end:
        warnings.append("period_unparsed")
    if row.get("total") and total is None:
        warnings.append("total_value_unparsed")
    if fold(row.get("country", "")) == "polska" and row.get("region") and not voivs:
        warnings.append("region_unparsed")

    content_hash = hashlib.sha256(json.dumps(row, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return {
        "schema": RECORD_SCHEMA,
        "source": SOURCE,
        "source_name": SOURCE_NAME,
        "record_id": record_id(number) or f"row-{excel_row}",
        "url": None,  # the source has no page per project; see list_url and provenance.source_file_url
        "list_url": LIST_URL,
        "content_hash": content_hash,
        "record_type": "eu_funded_project",
        "language": "pl",
        "title": title,
        "intro": None,
        "text": {"description": desc or None, "other": []},
        "text_for_llm": text_for_llm,
        "organizations": orgs,
        "people": [],
        "funding": {
            "operator": "Interreg",
            "programme": row.get("programme") or None,
            "contest": None,
            "project_no": number or None,
            "fund": row.get("fund") or None,
            "specific_objective": row.get("objective") or None,
            "intervention_field": row.get("intervention") or None,
            "strategic_project": _flag(row.get("strategic", "")),
            "above_5m_eur": _flag(row.get("above_5m", "")),
            "total_value": total,
            "grant_value": grant,
            "grant_value_computed": grant is not None,
            "currency": "EUR",
            "grant_share": round(rate / 100, 4) if rate is not None else None,
            "raw": {"total_value": row.get("total") or None, "eu_rate": row.get("eu_rate") or None},
        },
        "period": {
            "start": start.isoformat() if start else None,
            "end": end.isoformat() if end else None,
            "precision": "day" if start or end else None,
            "status": status,
            "ongoing": False,
            "raw": f"{row.get('start', '')} – {row.get('end', '')} (dni Excela)",
        },
        "region": {"voivodeships": voivs, "nationwide": False, "raw": row.get("region") or None,
                   "country": row.get("country") or None},
        "keywords": [],
        "extra": {},
        "rights": {
            "licence": "unknown",
            "llm_may_read_fulltext": True,
            "note": "Wykaz projektów publikowany przez instytucję zarządzającą (art. 49 CPR); warunki ponownego wykorzystania do potwierdzenia.",
        },
        "quality": {
            "status": "needs_review" if blocking else "ok",
            "blocking": blocking,
            "warnings": warnings,
            "narrative_chars": len(desc),
        },
        "provenance": {
            "connector": f"radar.sources.interreg/{CONNECTOR_VERSION}",
            "list_fetched_at": list_fetched_at,
            "detail_fetched_at": file_fetched_at,
            "source_file_url": file_url,
            "source_row": excel_row,
            "raw_files": raw_files or {},
        },
    }


# --- raw store + harvest -------------------------------------------------------
class RawStore:
    """list.html + the downloaded XLSX (original file name) + small meta files."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def _meta(self, name: str) -> Path:
        return self.root / f"{name}.meta.json"

    def save_page(self, resp: Response) -> dict:
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "list.html").write_text(resp.text, "utf-8")
        meta = {"url": resp.url, "status": resp.status, "fetched_at": resp.fetched_at, "path": str(self.root / "list.html")}
        self._meta("list").write_text(json.dumps(meta, ensure_ascii=False, indent=1), "utf-8")
        return meta

    def save_file(self, resp: BinaryResponse) -> dict:
        name = re.sub(r"[^\w.\-]+", "_", resp.url.rsplit("/", 1)[-1]) or "wykaz.xlsx"
        path = self.root / name
        path.write_bytes(resp.content)
        meta = {"url": resp.url, "status": resp.status, "fetched_at": resp.fetched_at, "path": str(path),
                "sha256": hashlib.sha256(resp.content).hexdigest(), "bytes": len(resp.content)}
        self._meta("file").write_text(json.dumps(meta, ensure_ascii=False, indent=1), "utf-8")
        return meta

    def load(self, name: str) -> dict | None:
        p = self._meta(name)
        if not p.exists():
            return None
        meta = json.loads(p.read_text("utf-8"))
        if meta.get("path"):
            # the saved file sits next to its meta file; a path written on another OS
            # (e.g. Windows backslashes read inside a Linux container) would not resolve
            meta["path"] = str(self.root / re.split(r"[\\/]", meta["path"])[-1])
        return meta


@dataclass
class HarvestStats:
    rows: int = 0
    records: int = 0
    duplicates: int = 0
    status: Counter = field(default_factory=Counter)
    reasons: Counter = field(default_factory=Counter)
    file_url: str | None = None
    missing_columns: list = field(default_factory=list)

    def summary(self) -> str:
        lines = [f"file: {self.file_url}", f"rows: {self.rows}, records: {self.records} (duplicates skipped: {self.duplicates})",
                 "missing columns: " + (", ".join(self.missing_columns) or "none"),
                 "quality: " + ", ".join(f"{k}={v}" for k, v in self.status.most_common())]
        if self.reasons:
            lines.append("reasons: " + ", ".join(f"{k}={v}" for k, v in self.reasons.most_common()))
        return "\n".join(lines)


def harvest(store: RawStore, *, page_fetcher: Callable[[str], Response] = fetch,
            file_fetcher: Callable[[str], BinaryResponse] = fetch_bytes, offline: bool = False,
            today: date | None = None, stats: HarvestStats | None = None) -> Iterator[dict]:
    stats = stats if stats is not None else HarvestStats()
    if offline:
        page_meta, file_meta = store.load("list"), store.load("file")
        if not file_meta:
            raise FileNotFoundError(f"brak zapisanego pliku w {store.root} (uruchom raz bez --offline)")
    else:
        page = page_fetcher(LIST_URL)
        page_meta = store.save_page(page)
        file_url = find_xlsx_link(page.text)
        if not file_url:
            raise FormatChanged(f"na stronie {LIST_URL} nie ma linku do pliku .xlsx")
        file_meta = store.save_file(file_fetcher(file_url))
    stats.file_url = file_meta["url"]
    rows = read_rows(Path(file_meta["path"]).read_bytes())
    mapping, data = parse_sheet(rows)
    stats.missing_columns = [k for k, _ in HEADERS if k not in mapping]
    stats.rows = len(data)
    raw_files = {"list_page": (page_meta or {}).get("path"), "source_file": file_meta["path"]}
    seen: set[str] = set()
    for excel_row, values in data:
        rec = build_record(values, excel_row=excel_row, file_url=file_meta["url"],
                           list_fetched_at=(page_meta or {}).get("fetched_at"),
                           file_fetched_at=file_meta.get("fetched_at"), raw_files=raw_files, today=today)
        if rec["record_id"] in seen:
            stats.duplicates += 1
            continue
        seen.add(rec["record_id"])
        stats.records += 1
        stats.status[rec["quality"]["status"]] += 1
        for r in rec["quality"]["blocking"]:
            stats.reasons[r] += 1
        yield rec


CSV_COLUMNS = ["record_id", "title", "programme", "lead_partner", "country", "voivodeship", "total_eur",
               "eu_rate", "start", "end", "status", "quality", "reasons"]


def _csv_row(r: dict) -> dict:
    lead = next((o for o in r["organizations"] if o["role"] == "lead_partner"), {})
    return {
        "record_id": r["record_id"], "title": r["title"], "programme": r["funding"]["programme"],
        "lead_partner": lead.get("name"), "country": r["region"]["country"],
        "voivodeship": ", ".join(r["region"]["voivodeships"]), "total_eur": r["funding"]["total_value"],
        "eu_rate": r["funding"]["raw"]["eu_rate"], "start": r["period"]["start"], "end": r["period"]["end"],
        "status": r["period"]["status"], "quality": r["quality"]["status"],
        "reasons": "; ".join(r["quality"]["blocking"] + r["quality"]["warnings"]),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="data/normalized/interreg.jsonl")
    ap.add_argument("--csv", default=None)
    ap.add_argument("--raw-dir", default="data/raw/interreg")
    ap.add_argument("--offline", action="store_true", help="use the saved page and file only, no network")
    args = ap.parse_args(argv)

    stats = HarvestStats()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    rows = []
    with tmp.open("w", encoding="utf-8") as fh:
        for rec in harvest(RawStore(Path(args.raw_dir)), offline=args.offline, stats=stats):
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
