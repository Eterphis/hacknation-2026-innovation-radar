"""Parsing of Polish-formatted values: money, dates and periods, voivodeships."""

from __future__ import annotations

import calendar
import difflib
import re
from dataclasses import asdict, dataclass
from datetime import date

from .text import fold

MONTHS = {
    # genitive and nominative forms, folded to ASCII
    "stycznia": 1, "styczen": 1, "lutego": 2, "luty": 2, "marca": 3, "marzec": 3,
    "kwietnia": 4, "kwiecien": 4, "maja": 5, "maj": 5, "czerwca": 6, "czerwiec": 6,
    "lipca": 7, "lipiec": 7, "sierpnia": 8, "sierpien": 8, "wrzesnia": 9, "wrzesien": 9,
    "pazdziernika": 10, "pazdziernik": 10, "listopada": 11, "listopad": 11,
    "grudnia": 12, "grudzien": 12,
}

VOIVODESHIPS = {
    "dolnoslaskie": "dolnośląskie",
    "kujawsko-pomorskie": "kujawsko-pomorskie",
    "lubelskie": "lubelskie",
    "lubuskie": "lubuskie",
    "lodzkie": "łódzkie",
    "malopolskie": "małopolskie",
    "mazowieckie": "mazowieckie",
    "opolskie": "opolskie",
    "podkarpackie": "podkarpackie",
    "podlaskie": "podlaskie",
    "pomorskie": "pomorskie",
    "slaskie": "śląskie",
    "swietokrzyskie": "świętokrzyskie",
    "warminsko-mazurskie": "warmińsko-mazurskie",
    "wielkopolskie": "wielkopolskie",
    "zachodniopomorskie": "zachodniopomorskie",
}
_NATIONWIDE = ("cala polska", "caly kraj", "ogolnopolsk", "polska")


# money ----------------------------------------------------------------------
def parse_money(raw: str | None) -> tuple[float | None, str | None]:
    """'1 186 431,74 zł' -> (1186431.74, 'PLN'). Returns (None, None) when no number is found."""
    if not raw:
        return None, None
    f = fold(raw)
    currency = "PLN" if re.search(r"\bzl\b|\bpln\b|zl\.?$", f) else ("EUR" if re.search(r"\beur\b|€", f) else None)
    m = re.search(r"\d[\d\s.,]*", raw.replace(" ", " "))
    if not m:
        return None, currency
    num = re.sub(r"\s", "", m.group(0)).rstrip(".,")
    if "," in num:
        num = num.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", num):
        num = num.replace(".", "")
    try:
        return round(float(num), 2), currency or "PLN"
    except ValueError:
        return None, currency


# dates ----------------------------------------------------------------------
@dataclass
class Period:
    start: str | None
    end: str | None
    precision: str | None  # day | month | year (of the less precise end)
    status: str | None  # planned | running | finished
    ongoing: bool
    raw: str

    def as_dict(self) -> dict:
        return asdict(self)


_PRECISION_RANK = {"day": 0, "month": 1, "year": 2}


def _parse_date(text: str, is_end: bool) -> tuple[date | None, str | None]:
    # (?<!\d)/(?!\d) instead of \b: pages write "2017r." and "listopada2017" without spaces
    t = fold(text)
    m = re.search(r"(?<!\d)(\d{1,2})\s*[.\-/]\s*(\d{1,2})\s*[.\-/]\s*(\d{4})(?!\d)", t)
    if m:
        d, mo, y = map(int, m.groups())
        return _safe_date(y, mo, d), "day"
    m = re.search(r"(?<!\d)(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})(?!\d)", t)
    if m:
        y, mo, d = map(int, m.groups())
        return _safe_date(y, mo, d), "day"
    m = re.search(r"(?<!\d)(\d{1,2})\s*([a-z]+)\s*(\d{4})(?!\d)", t)
    if m and m.group(2) in MONTHS:
        return _safe_date(int(m.group(3)), MONTHS[m.group(2)], int(m.group(1))), "day"
    m = re.search(r"\b([a-z]+)\s*(\d{4})(?!\d)", t)
    if m and m.group(1) in MONTHS:
        y, mo = int(m.group(2)), MONTHS[m.group(1)]
        d = calendar.monthrange(y, mo)[1] if is_end else 1
        return _safe_date(y, mo, d), "month"
    m = re.search(r"(?<!\d)(\d{1,2})[.\-/](\d{4})(?!\d)", t)
    if m:
        mo, y = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12:
            d = calendar.monthrange(y, mo)[1] if is_end else 1
            return _safe_date(y, mo, d), "month"
    m = re.search(r"(?<!\d)(19|20)(\d{2})(?!\d)", t)
    if m:
        y = int(m.group(0))
        return (date(y, 12, 31) if is_end else date(y, 1, 1)), "year"
    return None, None


def _safe_date(y: int, mo: int, d: int) -> date | None:
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def parse_period(raw: str | None, today: date | None = None) -> Period:
    """Handles 'od 01.02.2016 r. do 31.01.2019 r.', '01.10.2019 - 31.03.2022',
    'od 1 grudnia 2018r. do 31 października 2021r.', 'Od 2018 r. – projekt w toku'."""
    raw = raw or ""
    today = today or date.today()
    f = fold(raw)
    ongoing = bool(re.search(r"w toku|trwa|obecnie|nadal|do chwili obecnej", f))
    parts = [raw]
    for sep in (r"\s+do\s+", r"\s+[-–—]\s+", r"(?<=\d{4})\s*[-–—]\s*(?=\d)"):
        parts = re.split(sep, raw, maxsplit=1, flags=re.I)
        if len(parts) > 1:
            break
    start_txt = parts[0]
    end_txt = parts[1] if len(parts) > 1 else ""
    start, p1 = _parse_date(start_txt, is_end=False)
    end, p2 = _parse_date(end_txt, is_end=True) if end_txt else (None, None)
    precisions = [p for p in (p1, p2) if p]
    precision = max(precisions, key=_PRECISION_RANK.__getitem__) if precisions else None
    if start and end and end < start:
        start, end = end, start
    if ongoing and not end:
        status = "running"
    elif end and end < today:
        status = "finished"
    elif start and start > today:
        status = "planned"
    elif start:
        status = "running"
    else:
        status = None
    return Period(
        start=start.isoformat() if start else None,
        end=end.isoformat() if end else None,
        precision=precision,
        status=status,
        ongoing=ongoing,
        raw=raw,
    )


# regions --------------------------------------------------------------------
def parse_voivodeships(raw: str | None) -> tuple[list[str], bool]:
    """'województwo lubelskie' -> (['lubelskie'], False); 'cała Polska' -> ([], True).

    Longest names are matched first so 'kujawsko-pomorskie' does not also yield 'pomorskie'.
    """
    if not raw:
        return [], False
    f = fold(raw)
    f = re.sub(r"(warminsko|kujawsko)\s+", r"\1-", f)  # "warmińsko mazurskie"
    found: list[tuple[int, str]] = []
    taken = [False] * len(f)
    for key in sorted(VOIVODESHIPS, key=len, reverse=True):
        for m in re.finditer(rf"(?<![a-z-]){re.escape(key)}(?![a-z-])", f):
            if not any(taken[m.start():m.end()]):
                found.append((m.start(), VOIVODESHIPS[key]))
                for i in range(m.start(), m.end()):
                    taken[i] = True
    if not found:  # typos such as "zachodnioporskie": close match on long words only
        for m in re.finditer(r"[a-z]+(?:-[a-z]+)?", f):
            if len(m.group(0)) >= 7:
                close = difflib.get_close_matches(m.group(0), VOIVODESHIPS, n=1, cutoff=0.88)
                if close:
                    found.append((m.start(), VOIVODESHIPS[close[0]]))
    names = [name for _, name in sorted(found)]
    names = list(dict.fromkeys(names))
    nationwide = not names and any(n in f for n in _NATIONWIDE)
    return names, nationwide
