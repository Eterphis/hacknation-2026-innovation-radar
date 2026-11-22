"""Calls for proposals (nabory) from the published schedules of EU funds 2021-2027, no LLM.

Every managing authority must publish a schedule of calls (art. 49 CPR 2021/1060). They are published as DOCX/PDF
tables on funduszeeuropejskie.gov.pl and the regional programme sites; there is no feed or API (checked 2026-11-22).
This module reads such tables, from DOCX (stdlib zipfile + XML) or CSV (an exported or hand-saved table), with
columns found by name, so the national programmes (FENG, FERS, FEnIKS, FEPW) and the 16 regional ones fit:

- `parse_docx(bytes)` / `parse_csv(text)` -> rows (header -> cell), `calls_from_rows(rows, source)` -> call dicts:
  programme, action, title, applicants (raw + Basal institution types), sectors (Basal keyword rules), voivodeship
  (from the regional programme's name), start/end dates (day, month or quarter precision), allocation, source and
  fetch date.
- `CallsSource.from_env()` reads RADAR_CALLS_URLS (comma-separated schedule URLs) and the local directory
  RADAR_CALLS_DIR (default data/import/nabory); none configured -> no calls, nothing breaks (`optional`).
  Parsed calls are cached on disk per URL for a day.
- `upcoming(calls, sector=, institution_type=, voivodeship=, today=)` -> the nearest open or planned calls for an
  idea, each with the reasons it matched. Storing calls in the `calls` table waits for migration 0006 (after #36).
"""

from __future__ import annotations

import csv
import hashlib
import io
import os
import re
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

from radar.basal import taxonomy as T
from radar.basal.embed import fold
from radar.sources.disk_cache import DiskCache

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
COLUMNS = {  # field -> (folded header prefixes, folded fragments anywhere in the header); dates first
    "start": (("planowany termin rozpocz", "termin rozpocz", "data rozpocz", "rozpoczec", "poczatek"), ("rozpocz",)),
    "end": (("planowany termin zakoncz", "termin zakoncz", "data zakoncz", "zakoncz", "koniec"), ("zakoncz",)),
    "amount": (("kwota", "alokac", "budzet", "wartosc"), ("kwot", "alokac")),
    "applicants": (("typ wnioskodaw", "typy wnioskodaw", "wnioskodaw", "potencjaln", "kto moze", "beneficjen"), ("wnioskodaw",)),
    "programme": (("program",), ()),
    "priority": (("priorytet",), ()),
    "action": (("numer i nazwa dzialani", "nazwa dzialani", "dzialani"), ()),
    "title": (("nazwa nabor", "typ projekt", "typy projekt", "przedmiot", "tytul", "zakres", "nabor"), ()),
    "institution": (("instytucj",), ()),
    "url": (("link", "adres", "url"), ()),
}
MONTHS = {"stycz": 1, "luty": 2, "lut": 2, "marz": 3, "mar": 3, "kwie": 4, "maj": 5, "czerw": 6, "lip": 7, "sierp": 8,
          "wrzes": 9, "pazdz": 10, "listop": 11, "grud": 12}
QUARTERS = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "1": 1, "2": 2, "3": 3, "4": 4}
REGIONAL = [  # folded fragment of the programme name -> voivodeship (longer names first)
    ("pomorza zachodn", "zachodniopomorskie"), ("kujaw i pomorza", "kujawsko-pomorskie"), ("warmii i mazur", "warmińsko-mazurskie"),
    ("dolnego slaska", "dolnośląskie"), ("lubelskiego", "lubelskie"), ("lubuskie", "lubuskie"), ("lodzkiego", "łódzkie"),
    ("malopolski", "małopolskie"), ("mazowsza", "mazowieckie"), ("opolskiego", "opolskie"), ("podkarpacia", "podkarpackie"),
    ("podlaskiego", "podlaskie"), ("slaskiego", "śląskie"), ("swietokrzyskiego", "świętokrzyskie"), ("wielkopolski", "wielkopolskie"),
    ("pomorza", "pomorskie"),
]
EASTERN = ["lubelskie", "podkarpackie", "podlaskie", "świętokrzyskie", "warmińsko-mazurskie"]  # FEPW
APPLICANTS = {  # Basal institution type -> folded regexes over the applicants column
    "jst": [r"\bjst\b", r"samorzad", r"\bgmin", r"powiat", r"wojewodztw", r"zwiaz\w* (gmin|komunaln)"],
    "uczelnia": [r"uczelni", r"szkol\w* wyzsz", r"uniwersytet"],
    "instytut": [r"instytut", r"jednost\w* naukow", r"organizacj\w* badawcz", r"sieci badawcz", r"\bpan\b"],
    "firma": [r"przedsiebior", r"\bmsp\b",r"mikro", r"\bfirm", r"spolk"],
    "szkola": [r"szkol(?!\w* wyzsz)", r"placow\w* oswiat", r"przedszkol", r"organ\w* prowadzac"],
    "inna_publiczna": [r"pozarzadow", r"\bngo\b", r"jednost\w* sektora finansow", r"podmiot\w* lecznicz", r"szpital",
                       r"instytucj\w* kultury", r"administracj"],
}


# ------------------------------------------------------------------------------------------- reading tables
def parse_docx(data: bytes) -> list[list[list[str]]]:
    """All tables of a DOCX as rows of cell texts."""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    tables = []
    for tbl in root.iter(f"{W}tbl"):
        rows = []
        for tr in tbl.iter(f"{W}tr"):
            cells = []
            for tc in tr.findall(f"{W}tc"):
                paras = ["".join(t.text or "" for t in p.iter(f"{W}t")) for p in tc.iter(f"{W}p")]
                cells.append(" ".join(" ".join(paras).split()))
            if any(cells):
                rows.append(cells)
        if rows:
            tables.append(rows)
    return tables


def parse_csv(text: str) -> list[list[str]]:
    sample = text[:4000]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t")
    except csv.Error:
        dialect = csv.excel
    return [[c.strip() for c in row] for row in csv.reader(io.StringIO(text.lstrip("﻿")), dialect) if any(row)]


def _header_map(header: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    folded = [fold(h) for h in header]
    for field, (prefixes, fragments) in COLUMNS.items():
        used = set(out.values())
        hit = next((i for p in prefixes for i, h in enumerate(folded) if h.startswith(p) and i not in used), None)
        if hit is None:
            hit = next((i for p in fragments for i, h in enumerate(folded) if p in h and i not in used), None)
        if hit is not None:
            out[field] = hit
    return out


def rows_to_dicts(table: list[list[str]]) -> list[dict]:
    """Find the header row (the first one naming a title/action column and a date column) and map the rest."""
    for i, row in enumerate(table[:6]):
        m = _header_map(row)
        if ("title" in m or "action" in m) and ("start" in m or "end" in m):
            return [{f: (r[j] if j < len(r) else "") for f, j in m.items()} for r in table[i + 1:]]
    return []


# ------------------------------------------------------------------------------------------- normalizing
def parse_when(text: str | None, end: bool = False) -> tuple[str | None, str | None]:
    """'15.03.2026' | '2026-03-15' | 'marzec 2026' | 'III kwartał 2026' -> (ISO date, precision)."""
    t = fold(text or "")
    if not t:
        return None, None
    if m := re.search(r"(\d{4})-(\d{2})-(\d{2})", text or ""):
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}", "day"
    if m := re.search(r"\b(\d{1,2})[./](\d{1,2})[./](\d{4})", text or ""):
        return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}", "day"
    year = re.search(r"\b(20\d{2})\b", t)
    if not year:
        return None, None
    y = int(year.group(1))
    if m := re.search(r"\b(iv|iii|ii|i|[1-4])\s*(kw|kwarta)", t):
        q = QUARTERS[m.group(1)]
        mon = q * 3 if end else q * 3 - 2
        return _month_edge(y, mon, end), "quarter"
    if m := re.search(r"\b(\d{1,2})[./]" + str(y), t):
        return _month_edge(y, int(m.group(1)), end), "month"
    for stem, mon in MONTHS.items():
        if re.search(rf"\b{stem}", t):
            return _month_edge(y, mon, end), "month"
    return (f"{y}-12-31" if end else f"{y}-01-01"), "year"


def _month_edge(y: int, m: int, end: bool) -> str:
    if not end:
        return f"{y}-{m:02d}-01"
    nxt = date(y + (m == 12), m % 12 + 1, 1)
    return date.fromordinal(nxt.toordinal() - 1).isoformat()


def _amount(text: str | None) -> float | None:
    t = (text or "").lower().replace("\xa0", " ")
    m = re.search(r"(\d[\d \.]*(?:,\d+)?)\s*(mld|mln|tys)?", t)
    if not m:
        return None
    try:
        v = float(m.group(1).replace(" ", "").replace(".", "").replace(",", "."))
    except ValueError:
        return None
    return v * {"mld": 1e9, "mln": 1e6, "tys": 1e3}.get(m.group(2) or "", 1)


def voivodeships_of(programme: str | None) -> list[str] | None:
    """Regional programme -> [its voivodeship]; FEPW -> eastern Poland; national programmes -> None (whole country)."""
    f = fold(programme or "")
    if re.search(r"polsk\w* wschodni", f) or "fepw" in f:
        return EASTERN
    for frag, woj in REGIONAL:
        if frag in f:
            return [woj]
    return None


def applicant_types(text: str | None) -> list[str]:
    f = fold(text or "")
    return [k for k, pats in APPLICANTS.items() if any(re.search(p, f) for p in pats)]


def sectors_of(text: str | None) -> list[str]:
    f = fold(text or "")
    hits = []
    for code, spec in T.SECTORS.items():
        n = sum(bool(re.search(p, f)) for p in spec.get("kw", []))
        if n:
            hits.append((n, code))
    return [c for _, c in sorted(hits, reverse=True)[:3]]


def calls_from_rows(rows: list[dict], source: str, fetched_at: str | None = None, programme: str | None = None) -> list[dict]:
    out = []
    for r in rows:
        title = r.get("title") or r.get("action") or ""
        start, sp = parse_when(r.get("start"))
        end, ep = parse_when(r.get("end"), end=True)
        if not title.strip() or not (start or end):
            continue
        prog = r.get("programme") or programme
        text = " ".join(filter(None, [r.get("priority"), r.get("action"), title]))
        cid = hashlib.sha256(f"{prog}|{r.get('action')}|{title}|{start}|{end}".encode("utf-8")).hexdigest()[:16]
        out.append({"id": cid, "programme": prog, "action": r.get("action") or None, "title": " ".join(title.split())[:400],
                    "applicants": r.get("applicants") or None, "applicant_types": applicant_types(r.get("applicants")),
                    "sectors": sectors_of(text), "voivodeships": voivodeships_of(prog),
                    "start": start, "start_precision": sp, "end": end, "end_precision": ep,
                    "amount_pln": _amount(r.get("amount")), "institution": r.get("institution") or None,
                    "url": r.get("url") or None, "source": source, "fetched_at": fetched_at})
    return out


def calls_from_bytes(data: bytes, name: str, source: str, fetched_at: str | None = None) -> list[dict]:
    """A schedule file (DOCX or CSV) -> calls. The programme can come from the file name when no column has it."""
    programme = Path(name).stem.replace("_", " ").replace("-", " ") if voivodeships_of(name) or "fe" in fold(name) else None
    if name.lower().endswith(".docx"):
        rows = [d for t in parse_docx(data) for d in rows_to_dicts(t)]
    else:
        for enc in ("utf-8-sig", "cp1250"):
            try:
                text = data.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        rows = rows_to_dicts(parse_csv(text))
    return calls_from_rows(rows, source, fetched_at, programme)


# ------------------------------------------------------------------------------------------- fetching
class CallsSource:
    def __init__(self, urls: list[str], local_dir: Path | None, cache: DiskCache | None = None, http=None):
        self.urls, self.local_dir = urls, local_dir
        self.cache = cache or DiskCache("calls", ttl_s=86400)
        self.http = http

    @classmethod
    def from_env(cls, **kw) -> "CallsSource":
        urls = [u.strip() for u in os.environ.get("RADAR_CALLS_URLS", "").split(",") if u.strip()]
        d = Path(os.environ.get("RADAR_CALLS_DIR") or Path(__file__).resolve().parents[3] / "data" / "import" / "nabory")
        return cls(urls, d, **kw)

    def load(self) -> list[dict]:
        """All calls from the configured schedules; a failing URL or file is skipped (optional source)."""
        import httpx

        calls: list[dict] = []
        for url in self.urls:
            def get(url=url):
                c = self.http or httpx.Client(timeout=60, follow_redirects=True, headers={"User-Agent": "innovation-radar/1.0 (+calls)"})
                r = c.get(url)
                r.raise_for_status()
                return calls_from_bytes(r.content, url.split("?")[0], url)
            try:
                entry = self.cache.fetch(f"url:{url}", get)
            except (httpx.HTTPError, zipfile.BadZipFile, ET.ParseError, KeyError):
                continue
            calls += [{**c, "fetched_at": c.get("fetched_at") or entry["fetched_at"]} for c in entry["value"]]
        if self.local_dir and self.local_dir.is_dir():
            for p in sorted(self.local_dir.glob("*")):
                if p.suffix.lower() not in (".docx", ".csv"):
                    continue
                try:
                    at = datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")
                    calls += calls_from_bytes(p.read_bytes(), p.name, f"plik {p.name}", at)
                except (OSError, zipfile.BadZipFile, ET.ParseError, KeyError):
                    continue
        seen, out = set(), []
        for c in calls:
            if c["id"] not in seen:
                seen.add(c["id"])
                out.append(c)
        return out


# ------------------------------------------------------------------------------------------- matching
def upcoming(calls: list[dict], sector: str | None = None, institution_type: str | None = None,
             voivodeship: str | None = None, today: date | None = None, n: int = 5) -> list[dict]:
    """Nearest open or planned calls for an idea: not closed, in its region (or nationwide), and matching its
    sector or institution type. Each item says why it matched."""
    today = today or date.today()
    woj = T.VOIVODESHIPS.get(fold(voivodeship or "").strip(), voivodeship)
    out = []
    for c in calls:
        if c.get("end") and c["end"] < today.isoformat():
            continue
        if not c.get("end") and c.get("start") and c["start"] < date.fromordinal(today.toordinal() - 60).isoformat():
            continue
        if c.get("voivodeships") and woj not in c["voivodeships"]:
            continue
        why, score = [], 0.0
        if sector and sector in (c.get("sectors") or []):
            score += 2; why.append("sektor")
        if institution_type and institution_type in (c.get("applicant_types") or []):
            score += 2; why.append("typ wnioskodawcy")
        elif not c.get("applicant_types"):
            score += .5
        if c.get("voivodeships") and woj in c["voivodeships"]:
            score += 1; why.append(f"program regionalny ({woj})")
        if score < 2:
            continue
        is_open = bool(c.get("start") and c["start"] <= today.isoformat())
        out.append({**c, "match": score, "why": why, "status": "trwa" if is_open else "planowany"})
    out.sort(key=lambda c: (-c["match"], c["status"] != "trwa", c.get("start") or "9999", c.get("end") or "9999"))
    return out[:n]
