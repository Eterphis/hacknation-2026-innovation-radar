"""Fundusze Europejskie 2021–2027: list of projects co-financed in Poland -> normalized records.

Source: dane.gov.pl dataset 13939 "Lista beneficjentów (projektów) Funduszy Europejskich 2021-2027"
(publisher: Ministerstwo Funduszy i Polityki Regionalnej, licence CC0 1.0, updated quarterly). The
dataset holds one XLSX resource that is replaced by a new resource (new id, new file name with the
date) on every update, so the file is located through the dane.gov.pl API on every run:

    https://api.dane.gov.pl/1.4/datasets/13939/resources?sort=-data_date
      -> newest resource with format xlsx -> attributes.download_url
      -> 302 to https://api.dane.gov.pl/media/resources/<YYYYMMDD>/Lista_projektow_FE_2021_2027_<DDMMYYYY>.xlsx

No login is needed. The file is ~40 MB (all programmes: FENG, FERS, FEnIKS, FERC, FEPW, the 16 regional
programmes, Interreg is not included). The download is conditional (ETag / Last-Modified), so an
unchanged file costs one small request.

Import mode: with `--import` (or when `--offline` finds no downloaded file) every `.xlsx`/`.csv` in
`data/import/fe/` is read instead, e.g. a file saved by hand from funduszeeuropejskie.gov.pl or an
older list. Columns are matched by name, so the same parser handles both.

Run:  python -X utf8 -m radar.sources.fe_projects --out data/normalized/fe.jsonl [--import]
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

from .. import RECORD_SCHEMA
from ..http import Response, fetch
from ..pl import parse_voivodeships
from ..text import clean_text, fold
from ..xlsx import excel_date, iter_rows
from .dumps import HeaderMap, download_if_changed, file_meta, import_files, num, read_csv_text, decode, saved_file, slug
from .ncbr import org_type_hint

SOURCE = "fe_2021_2027"
SOURCE_NAME = "Fundusze Europejskie 2021–2027 – lista projektów (dane.gov.pl)"
CONNECTOR_VERSION = "0.1.0"
CATEGORY = "projekty"
DATASET_ID = 13939
DATASET_URL = f"https://dane.gov.pl/pl/dataset/{DATASET_ID}"
RESOURCES_API = f"https://api.dane.gov.pl/1.4/datasets/{DATASET_ID}/resources?sort=-data_date&per_page=20"
IMPORT_DIR = Path("data/import/fe")
MIN_TEXT_CHARS = 200

ALIASES: list[tuple[str, tuple[str, ...]]] = [
    ("start", ("data rozpoczecia", "data poczatku")),
    ("end", ("data zakonczenia", "planowana data zakonczenia", "data konca")),
    ("signed", ("data podpisania", "data zawarcia")),
    ("beneficiary_nip", ("nip beneficjenta", "nip")),
    ("beneficiary_regon", ("regon",)),
    ("beneficiary_form", ("forma prawna", "typ beneficjenta", "rodzaj beneficjenta")),
    ("beneficiary", ("nazwa beneficjenta", "beneficjent", "nazwa wnioskodawcy")),
    ("partners", ("partnerzy", "nazwa partner", "partner")),
    ("contractor", ("nazwa wykonawcy", "wykonawca")),
    ("project_no", ("numer projektu", "nr projektu", "numer umowy", "numer wniosku", "kod projektu")),
    ("title", ("tytul projektu", "nazwa projektu", "tytul")),
    ("description", ("opis projektu", "opis", "cel projektu", "streszczenie")),
    ("programme", ("program", "nazwa programu")),
    ("priority", ("priorytet", "os priorytetowa")),
    ("measure", ("dzialanie", "poddzialanie")),
    ("objective", ("cel szczegolowy", "cel polityki")),
    ("fund", ("fundusz",)),
    ("intervention", ("kategoria wsparcia", "zakres interwencji", "obszar interwencji", "kategoria interwencji",
                      "dziedzina interwencji")),
    ("total", ("wartosc projektu", "calkowita wartosc", "wartosc ogolem", "koszt calkowity", "wydatki ogolem")),
    ("eligible", ("wydatki kwalifikowalne", "koszty kwalifikowalne", "wartosc wydatkow kwalifikowalnych")),
    ("eu_grant", ("dofinansowanie ue", "kwota dofinansowania ue", "wklad ue", "dofinansowanie z ue", "dofinansowanie unijne")),
    ("grant", ("dofinansowanie", "kwota dofinansowania")),
    ("eu_rate", ("poziom unijnego dofinansowania", "poziom dofinansowania", "stopa dofinansowania", "procent dofinansowania")),
    ("eur_rate", ("kurs euro",)),
    ("location", ("miejsce realizacji", "lokalizacja projektu")),
    ("voivodeship", ("wojewodztwo",)),
    ("powiat", ("powiat",)),
    ("gmina", ("gmina",)),
    ("city", ("miejscowosc", "miasto")),
    ("postal_code", ("kod pocztowy",)),
    ("status", ("status", "stan realizacji", "stan projektu")),
    ("strategic", ("projekt strategiczny", "strategiczny")),
]
REQUIRED = ("title", "beneficiary")


class FormatChanged(Exception):
    """The list no longer has a title and a beneficiary column, or the API no longer lists an XLSX."""


# --- locating the file --------------------------------------------------------------
def newest_xlsx(api_json: dict) -> dict | None:
    """From the dane.gov.pl resources answer: {'id', 'title', 'url', 'data_date'} of the newest XLSX."""
    best = None
    for r in api_json.get("data", []):
        a = r.get("attributes", {})
        if (a.get("format") or "").lower() != "xlsx" or not (a.get("download_url") or a.get("link")):
            continue
        cand = {"id": r.get("id"), "title": a.get("title"), "url": a.get("download_url") or a.get("link"),
                "data_date": a.get("data_date") or a.get("created") or ""}
        if best is None or cand["data_date"] > best["data_date"]:
            best = cand
    return best


# --- normalization --------------------------------------------------------------------
def parse_date(value: str | None) -> date | None:
    v = (value or "").strip()
    if not v:
        return None
    if re.fullmatch(r"\d+(\.\d+)?", v):
        return excel_date(v)
    m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", v) or None
    if m:
        y, mo, d = map(int, m.groups())
    else:
        m = re.match(r"(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})", v)
        if not m:
            return None
        d, mo, y = map(int, m.groups())
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def _rate(value: str | None) -> float | None:
    r = num((value or "").replace("%", ""))
    if r is None:
        return None
    return round(r / 100, 4) if r > 1 else round(r, 4)


def _flag(value: str | None) -> bool | None:
    f = fold(value or "")
    return True if f in ("t", "tak", "y", "yes", "true") else False if f in ("n", "nie", "no", "false") else None


def parse_location(raw: str | None) -> dict:
    """'WOJ.: LUBELSKIE, POW.: Biała Podlaska, GM.: Biała Podlaska | WOJ.: …' or 'Cały Kraj' ->
    {voivodeships, powiaty, gminy, nationwide}."""
    out = {"voivodeships": [], "powiaty": [], "gminy": [], "nationwide": False}
    if not raw:
        return out
    for part in re.split(r"\s*\|\s*", raw):
        for key, label in (("voivodeships", "WOJ"), ("powiaty", "POW"), ("gminy", "GM")):
            m = re.search(rf"\b{label}\.?:\s*([^,|]+)", part, re.I)
            if m and clean_text(m.group(1)) not in out[key]:
                out[key].append(clean_text(m.group(1)))
    voivs, nationwide = parse_voivodeships(" ; ".join(out["voivodeships"]) or raw)
    out["voivodeships"], out["nationwide"] = voivs, nationwide
    return out


def split_partners(raw: str | None) -> list[str]:
    return list(dict.fromkeys(clean_text(p) for p in re.split(r"\s*(?:;|\||\n)\s*", raw or "") if clean_text(p)))


def build_record(row: dict[str, str], *, file_row: int, file: dict, today: date | None = None) -> dict:
    today = today or date.today()
    title, desc = row.get("title", ""), row.get("description", "")
    number = row.get("project_no", "")
    start, end = parse_date(row.get("start")), parse_date(row.get("end"))
    status = None
    if end and end < today:
        status = "finished"
    elif start and start > today:
        status = "planned"
    elif start:
        status = "running"
    loc = parse_location(row.get("location") or row.get("voivodeship"))
    voivs, nationwide = loc["voivodeships"], loc["nationwide"]
    beneficiary = row.get("beneficiary", "")
    orgs = []
    if beneficiary:
        orgs.append({"name": beneficiary, "role": "beneficiary",
                     "type_hint": org_type_hint(beneficiary) or org_type_hint(row.get("beneficiary_form", "")),
                     "legal_form": row.get("beneficiary_form") or None,
                     "nip": re.sub(r"\D", "", row.get("beneficiary_nip", "")) or None,
                     "regon": re.sub(r"\D", "", row.get("beneficiary_regon", "")) or None,
                     "location": {k: row.get(k) or None for k in ("postal_code", "city", "gmina", "powiat")},
                     "org_id": None, "is_public": None})
    if row.get("contractor") and fold(row["contractor"]) != fold(beneficiary):
        orgs.append({"name": row["contractor"], "role": "contractor", "type_hint": org_type_hint(row["contractor"]),
                     "org_id": None, "is_public": None})
    for p in split_partners(row.get("partners")):
        if fold(p) != fold(beneficiary):
            orgs.append({"name": p, "role": "partner", "type_hint": org_type_hint(p), "org_id": None, "is_public": None})

    total, eligible = num(row.get("total")), num(row.get("eligible"))
    eu_grant, grant = num(row.get("eu_grant")), num(row.get("grant"))
    text_for_llm = "\n\n".join(x for x in [
        f"Tytuł: {title}",
        f"Opis projektu:\n{desc}" if desc else "",
        f"Beneficjent: {beneficiary}" if beneficiary else "",
        f"Program: {row['programme']}" + (f", działanie {row['measure']}" if row.get("measure") else "") if row.get("programme") else "",
        f"Zakres interwencji: {row['intervention']}" if row.get("intervention") else "",
    ] if x)

    blocking, warnings = [], []
    if not title:
        blocking.append("missing_title")
    if not number:
        warnings.append("missing_project_no")
    if len(desc) < MIN_TEXT_CHARS:
        blocking.append("short_text")
    if (row.get("start") and not start) or (row.get("end") and not end):
        warnings.append("period_unparsed")
    if (row.get("location") or row.get("voivodeship")) and not voivs and not nationwide:
        warnings.append("region_unparsed")

    rid = slug(number) or "row-" + hashlib.sha1(f"{beneficiary}|{title}".encode()).hexdigest()[:12]
    return {
        "schema": RECORD_SCHEMA,
        "source": SOURCE,
        "source_name": SOURCE_NAME,
        "record_id": rid,
        "url": None,  # the list has no page per project; see provenance.source_file_url
        "list_url": DATASET_URL,
        "content_hash": hashlib.sha256(json.dumps(row, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
        "record_type": "eu_funded_project",
        "language": "pl",
        "title": title,
        "intro": None,
        "text": {"description": desc or None, "other": []},
        "text_for_llm": text_for_llm,
        "organizations": orgs,
        "people": [],
        "funding": {
            "operator": "Fundusze Europejskie 2021–2027",
            "programme": row.get("programme") or None,
            "priority": row.get("priority") or None,
            "measure": row.get("measure") or None,
            "contest": None,
            "project_no": number or None,
            "fund": row.get("fund") or None,
            "specific_objective": row.get("objective") or None,
            "intervention_field": row.get("intervention") or None,
            "strategic_project": _flag(row.get("strategic")),
            "total_value": total,
            "eligible_value": eligible,
            "grant_value": eu_grant if eu_grant is not None else grant,
            "grant_value_eu": eu_grant,
            "grant_value_computed": False,
            "currency": "PLN",
            "eur_exchange_rate": num(row.get("eur_rate")),
            "grant_share": _rate(row.get("eu_rate")),
            "raw": {k: row.get(k) or None for k in ("total", "eligible", "eu_grant", "grant", "eu_rate")},
        },
        "period": {
            "start": start.isoformat() if start else None,
            "end": end.isoformat() if end else None,
            "precision": "day" if start or end else None,
            "status": status,
            "ongoing": False,
            "raw": f"{row.get('start', '')} – {row.get('end', '')}",
        },
        "region": {"voivodeships": voivs, "nationwide": nationwide, "powiaty": loc["powiaty"], "gminy": loc["gminy"],
                   "raw": row.get("location") or row.get("voivodeship") or None, "country": "Polska"},
        "keywords": [],
        "extra": {"category": CATEGORY, "status_raw": row.get("status") or None,
                  "signed": signed.isoformat() if (signed := parse_date(row.get("signed"))) else None},
        "rights": {"licence": "CC0 1.0" if file.get("url") else "unknown",
                   "llm_may_read_fulltext": True,
                   "note": "Lista projektów FE 2021–2027 publikowana przez MFiPR w dane.gov.pl (CC0 1.0)."
                   if file.get("url") else "Plik zaimportowany ręcznie; licencja według źródła pliku."},
        "quality": {"status": "needs_review" if blocking else "ok", "blocking": blocking, "warnings": warnings,
                    "narrative_chars": len(desc)},
        "provenance": {
            "connector": f"radar.sources.fe_projects/{CONNECTOR_VERSION}",
            "list_fetched_at": file.get("list_fetched_at") or file.get("fetched_at"),
            "detail_fetched_at": file.get("fetched_at"),
            "source_file_url": file.get("url"),
            "source_file": Path(file["path"]).name,
            "source_row": file_row,
            "raw_files": {"source_file": file["path"]},
        },
    }


# --- reading files ----------------------------------------------------------------------
def table_rows(path: Path) -> Iterator[list[str]]:
    path = Path(path)
    if path.suffix.lower() == ".csv":
        yield from read_csv_text(decode(path.read_bytes()))
    else:
        yield from iter_rows(path)


def parse_file(path: Path) -> tuple[HeaderMap, Iterator[tuple[int, dict[str, str]]]]:
    """Header found in the first 30 rows; data rows are then streamed (the national list is large)."""
    rows = table_rows(path)
    head: list[list[str]] = []
    for row in rows:
        head.append(row)
        if len(head) >= 30:
            break
    header = HeaderMap.find(head, ALIASES, REQUIRED)
    if header is None:
        raise FormatChanged(f"{path}: nie znaleziono nagłówka z kolumnami: " + ", ".join(REQUIRED))

    def data() -> Iterator[tuple[int, dict[str, str]]]:
        def all_rows():
            yield from head
            yield from rows
        for j, row in enumerate(all_rows(), start=1):
            if j <= header.header_row + 1:
                continue
            values = {k: clean_text(row[c]) if c < len(row) else "" for k, c in header.columns.items()}
            if any(values.values()):
                yield j, values
    return header, data()


# --- raw store + harvest ------------------------------------------------------------------
class RawStore:
    """The downloaded XLSX (`lista_projektow_fe.xlsx` + meta with ETag, resource id) and the API answer."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    @property
    def file(self) -> Path:
        return self.root / "lista_projektow_fe.xlsx"

    def save_api(self, resp: Response) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "resources.json").write_text(resp.text, "utf-8")


@dataclass
class HarvestStats:
    files: list = field(default_factory=list)
    rows: int = 0
    records: int = 0
    duplicates: int = 0
    status: Counter = field(default_factory=Counter)
    reasons: Counter = field(default_factory=Counter)
    programmes: Counter = field(default_factory=Counter)
    missing_columns: list = field(default_factory=list)

    def summary(self) -> str:
        lines = [f"file: {f.get('url') or f['path']} ({'pobrany' if f.get('changed') else 'bez zmian / z dysku / import'}, "
                 f"{f.get('bytes')} B)" for f in self.files]
        lines.append(f"rows: {self.rows}, records: {self.records} (duplicates skipped: {self.duplicates})")
        lines.append("missing columns: " + (", ".join(self.missing_columns) or "none"))
        lines.append("programmes: " + ", ".join(f"{k}={v}" for k, v in self.programmes.most_common(8)))
        lines.append("quality: " + ", ".join(f"{k}={v}" for k, v in self.status.most_common()))
        if self.reasons:
            lines.append("reasons: " + ", ".join(f"{k}={v}" for k, v in self.reasons.most_common()))
        return "\n".join(lines)


def harvest(store: RawStore, *, use_import: bool = False, import_dir: Path = IMPORT_DIR, offline: bool = False,
            force: bool = False, limit: int | None = None, today: date | None = None,
            api_fetcher: Callable[..., Response] = fetch, downloader: Callable[..., dict] = download_if_changed,
            stats: HarvestStats | None = None) -> Iterator[dict]:
    stats = stats if stats is not None else HarvestStats()
    if use_import:
        metas = [file_meta(p) for p in import_files(import_dir)]
        if not metas:
            raise FileNotFoundError(f"brak plików .xlsx/.csv w {import_dir}")
    elif offline:
        meta = saved_file(store.file)
        if not meta:
            raise FileNotFoundError(f"brak zapisanego pliku {store.file} (uruchom raz bez --offline albo użyj --import)")
        metas = [meta]
    else:
        resp = api_fetcher(RESOURCES_API, accept="application/vnd.api+json, application/json")
        store.save_api(resp)
        res = newest_xlsx(json.loads(resp.text))
        if not res:
            raise FormatChanged(f"zbiór {DATASET_URL} nie ma zasobu XLSX")
        meta = downloader(res["url"], store.file, expect_zip=True, force=force)
        meta.update(resource_id=res["id"], resource_title=res["title"], data_date=res["data_date"],
                    list_fetched_at=resp.fetched_at)
        metas = [meta]

    seen: set[str] = set()
    for meta in metas:  # import files: newest first, first occurrence of a project wins
        header, data = parse_file(Path(meta["path"]))
        stats.files.append(meta)
        stats.missing_columns = [k for k, _ in ALIASES if k not in header.columns]
        for file_row, values in data:
            stats.rows += 1
            rec = build_record(values, file_row=file_row, file=meta, today=today)
            if rec["record_id"] in seen:
                stats.duplicates += 1
                continue
            seen.add(rec["record_id"])
            stats.records += 1
            stats.status[rec["quality"]["status"]] += 1
            stats.programmes[rec["funding"]["programme"] or "?"] += 1
            for r in rec["quality"]["blocking"]:
                stats.reasons[r] += 1
            yield rec
            if limit is not None and stats.records >= limit:
                return


CSV_COLUMNS = ["record_id", "title", "beneficiary", "nip", "programme", "measure", "voivodeship", "total_pln",
               "eu_grant_pln", "start", "end", "status", "quality", "reasons"]


def _csv_row(r: dict) -> dict:
    b = next((o for o in r["organizations"] if o["role"] == "beneficiary"), {})
    f = r["funding"]
    return {"record_id": r["record_id"], "title": r["title"], "beneficiary": b.get("name"), "nip": b.get("nip"),
            "programme": f["programme"], "measure": f["measure"], "voivodeship": ", ".join(r["region"]["voivodeships"]),
            "total_pln": f["total_value"], "eu_grant_pln": f["grant_value_eu"], "start": r["period"]["start"],
            "end": r["period"]["end"], "status": r["period"]["status"], "quality": r["quality"]["status"],
            "reasons": "; ".join(r["quality"]["blocking"] + r["quality"]["warnings"])}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="data/normalized/fe.jsonl")
    ap.add_argument("--csv", default=None)
    ap.add_argument("--raw-dir", default="data/raw/fe")
    ap.add_argument("--offline", action="store_true", help="use the saved file only, no network")
    ap.add_argument("--import", dest="use_import", action="store_true", help=f"read files from --import-dir instead of dane.gov.pl")
    ap.add_argument("--import-dir", default=str(IMPORT_DIR))
    ap.add_argument("--force", action="store_true", help="download even if the server reports no change")
    ap.add_argument("--limit", type=int, default=None, help="stop after N records")
    args = ap.parse_args(argv)

    store = RawStore(Path(args.raw_dir))
    use_import = args.use_import or (args.offline and not store.file.exists() and bool(import_files(Path(args.import_dir))))
    stats = HarvestStats()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    rows = []
    with tmp.open("w", encoding="utf-8") as fh:
        for rec in harvest(store, use_import=use_import, import_dir=Path(args.import_dir), offline=args.offline,
                           force=args.force, limit=args.limit, stats=stats):
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
