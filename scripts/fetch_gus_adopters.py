"""One-off: potential adopters per voivodeship from GUS BDL -> app/radar/data/adopters.json.

Run by hand when you want fresher numbers (GUS publishes most of these yearly); the app only reads the JSON,
it never calls GUS at runtime.

    python -X utf8 scripts/fetch_gus_adopters.py                 # writes app/radar/data/adopters.json
    python -X utf8 scripts/fetch_gus_adopters.py --dry-run       # print the chosen variables and totals only

API: https://bdl.stat.gov.pl/api/v1 (Bank Danych Lokalnych). Anonymous use is limited (5 req/s, 100 per 15 min,
1000 per 12 h per IP). A free key (register at https://api.stat.gov.pl/Home/BdlApi) raises the limits: put it in
`.env` as GUS_BDL_CLIENT_ID=... (sent as the X-ClientId header, never printed or saved).

Each indicator names the BDL subject(s) and a name pattern; the matching variable's id is saved next to every
number (`variable_id`, `variable_ids`), with `source` and `fetched_at`. Unit levels: 0 = Polska, 2 = województwo. The latest year that has a value for Poland and for all 16
voivodeships is used, per variable.
No LLM, no scraping: only the public JSON API.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API = "https://bdl.stat.gov.pl/api/v1"
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "app" / "radar" / "data" / "adopters.json"
USER_AGENT = "innovation-radar-adopters/1.0 (one-off GUS BDL fetch)"

# TERYT voivodeship code (2 digits, BDL unit id positions 3-4) -> name used by the app (lower case, Polish)
VOIVODESHIPS = {
    "02": "dolnośląskie", "04": "kujawsko-pomorskie", "06": "lubelskie", "08": "lubuskie", "10": "łódzkie",
    "12": "małopolskie", "14": "mazowieckie", "16": "opolskie", "18": "podkarpackie", "20": "podlaskie",
    "22": "pomorskie", "24": "śląskie", "26": "świętokrzyskie", "28": "warmińsko-mazurskie",
    "30": "wielkopolskie", "32": "zachodniopomorskie",
}

# adopter key in app/radar/business.py -> label shown to users and the BDL variables summed for it.
# Each part is (subject id, regexes that must all match the variable's full name, regexes that must not match).
# Subjects were found with /subjects/search (2026-11-21). The variable inside a subject is chosen by name at run
# time and its id is saved, because GUS adds new variables to a subject when a classification changes. When a
# pattern matches zero or several variables the script stops and lists the candidates: fix the pattern, rerun.
TOTAL = r"(ogółem|razem)"
INDICATORS: dict[str, dict] = {
    "gminy": {"label": "gmin", "parts": [("P1413", [TOTAL], [r"miejsk", r"wiejsk"])]},
    "szkoly": {"label": "szkół podstawowych i ponadpodstawowych", "parts": [
        ("P2801", [TOTAL], [r"specjaln", r"dorosł", r"uczni", r"oddzia"]),
        ("P3477", [TOTAL], [r"specjaln", r"dorosł", r"uczni", r"oddzia", r"policealn"]),
    ]},
    "szpitale": {"label": "szpitali ogólnych", "parts": [("P1801", [r"szpital"], [r"łóżk", r"leczen", r"oddzia", r"na 10"])]},
    "biblioteki": {"label": "bibliotek publicznych (z filiami)", "parts": [("P1688", [r"bibliotek", r"filia|filiami"], [r"punkt", r"czytel", r"księgozb", r"wypożycz"])]},
    # REGON register by PKD 2007 section (all ownership sectors)
    "przemysl": {"label": "podmiotów przetwórstwa przemysłowego (sekcja C PKD, REGON)", "parts": [("P2809", [r"sekcja C\b", TOTAL], [r"dział", r"publiczn", r"prywatn"])]},
    "energetyka": {"label": "podmiotów energetyki (sekcja D PKD, REGON)", "parts": [("P2809", [r"sekcja D\b", TOTAL], [r"dział", r"publiczn", r"prywatn"])]},
    "firmy_ict": {"label": "firm informacji i komunikacji (sekcja J PKD, REGON)", "parts": [("P2809", [r"sekcja J\b", TOTAL], [r"dział", r"publiczn", r"prywatn"])]},
    "firmy_rolnictwo": {"label": "podmiotów rolnictwa (sekcja A PKD, REGON)", "parts": [("P2809", [r"sekcja A\b", TOTAL], [r"dział", r"publiczn", r"prywatn"])]},
    "firmy_budownictwo": {"label": "firm budowlanych (sekcja F PKD, REGON)", "parts": [("P2809", [r"sekcja F\b", TOTAL], [r"dział", r"publiczn", r"prywatn"])]},
}


def load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        m = re.match(r"^\s*(?:export\s+)?([A-Za-z_]\w*)\s*=\s*(.*?)\s*$", line)
        if m and not line.lstrip().startswith("#") and m.group(1) not in os.environ:
            v = m.group(2)
            os.environ[m.group(1)] = v[1:-1] if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"" else v


class Bdl:
    def __init__(self, client_id: str | None, pause: float):
        self.client_id, self.pause, self.calls = client_id, pause, 0

    def get(self, path: str, **params) -> dict:
        params = {"format": "json", "lang": "pl", **params}
        url = f"{API}/{path}?{urllib.parse.urlencode(params, doseq=True)}"
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        if self.client_id:
            headers["X-ClientId"] = self.client_id
        for attempt in range(4):
            if self.calls:
                time.sleep(self.pause)
            self.calls += 1
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as r:
                    return json.load(r)
            except urllib.error.HTTPError as e:
                if e.code != 429:
                    raise
                wait = e.headers.get("Retry-After", "")
                secs = int(re.sub(r"\D", "", wait) or 0)
                if secs > 120 or attempt == 3:
                    sys.exit(f"GUS BDL: limit zapytań wyczerpany (Retry-After: {wait or '?'}). "
                             "Ustaw GUS_BDL_CLIENT_ID w .env (darmowy klucz: https://api.stat.gov.pl/Home/BdlApi) "
                             "albo spróbuj później.")
                time.sleep(max(secs, 5))
        raise RuntimeError("unreachable")

    def pages(self, path: str, **params) -> list[dict]:
        out, page = [], 0
        while True:
            d = self.get(path, **{"page-size": 100, "page": page, **params})
            out += d.get("results") or []
            if not (d.get("links") or {}).get("next"):
                return out
            page += 1

    def variable(self, var_id: int) -> dict:
        return self.get(f"variables/{var_id}")

    def series(self, var_id: int, level: int) -> dict[str, dict[int, float]]:
        """unit id -> {year: value} for all units of one level."""
        res = {}
        for unit in self.pages(f"data/by-variable/{var_id}", **{"unit-level": level}):
            res[unit["id"]] = {int(v["year"]): v["val"] for v in unit.get("values") or [] if v.get("val") is not None}
        return res


def voivodeship_of(unit_id: str) -> str | None:
    # BDL level-2 ids look like "011200000000" (makroregion 01, województwo 12); the TERYT code is digits 3-4
    return VOIVODESHIPS.get(unit_id[2:4])


def latest_full_year(pl: dict[str, dict[int, float]], woj: dict[str, dict[int, float]]) -> int:
    years = set.intersection(*(set(v) for v in [*pl.values(), *woj.values()] if v)) if pl and woj else set()
    if not years:
        raise RuntimeError("no year with values for Poland and all voivodeships")
    return max(years)


def full_name(meta: dict) -> str:
    return " / ".join(str(meta[k]) for k in ("n1", "n2", "n3", "n4", "n5") if meta.get(k))


def pick_variable(bdl: Bdl, key: str, subject: str, include: list[str], exclude: list[str]) -> dict:
    variables = bdl.pages("variables", **{"subject-id": subject})
    hits = [v for v in variables
            if all(re.search(p, full_name(v), re.I) for p in include)
            and not any(re.search(p, full_name(v), re.I) for p in exclude)]
    if len(hits) != 1:
        listing = "\n".join(f"    {v['id']}: {full_name(v)}" for v in (hits or variables)[:60])
        sys.exit(f"{key}: w temacie {subject} {'brak pasującej zmiennej' if not hits else f'{len(hits)} pasujące zmienne'} "
                 f"(include={include}, exclude={exclude}). Kandydaci:\n{listing}\nPopraw wzorzec w INDICATORS.")
    return hits[0]


def fetch_indicator(bdl: Bdl, key: str, spec: dict, verbose: bool) -> dict:
    total, by_woj, parts = 0, {v: 0 for v in VOIVODESHIPS.values()}, []
    for subject, include, exclude in spec["parts"]:
        meta = pick_variable(bdl, key, subject, include, exclude)
        var_id, name = meta["id"], full_name(meta)
        pl, woj = bdl.series(var_id, 0), bdl.series(var_id, 2)
        woj = {u: v for u, v in woj.items() if voivodeship_of(u)}
        if len(woj) != 16:
            raise RuntimeError(f"{key}: variable {var_id} has {len(woj)} voivodeships, expected 16")
        year = latest_full_year(pl, woj)
        pl_val = sum(v[year] for v in pl.values())
        woj_vals = {voivodeship_of(u): v[year] for u, v in woj.items()}
        if abs(sum(woj_vals.values()) - pl_val) > max(2, pl_val * .01):
            print(f"  uwaga: {key}/{var_id}: suma województw {sum(woj_vals.values()):,.0f} != Polska {pl_val:,.0f}",
                  file=sys.stderr)
        total += pl_val
        for w, v in woj_vals.items():
            by_woj[w] += v
        parts.append({"variable_id": var_id, "name": name, "subject_id": meta.get("subjectId") or subject,
                      "year": year, "unit": meta.get("measureUnitName"), "poland": pl_val})
        if verbose:
            print(f"  {key}: {var_id} [{meta.get('subjectId')}] {name} ({year}): {pl_val:,.0f}", file=sys.stderr)
    years = sorted({p["year"] for p in parts})
    return {
        "label": spec["label"], "poland": round(total), "by_voivodeship": {w: round(v) for w, v in by_woj.items()},
        "year": years[-1], "years": years, "variable_id": parts[0]["variable_id"] if len(parts) == 1 else None,
        "variable_ids": [p["variable_id"] for p in parts], "variables": parts,
        "source": "GUS BDL, " + ", ".join(f"temat {p['subject_id']}, zmienna {p['variable_id']}" for p in parts),
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--only", nargs="+", choices=sorted(INDICATORS), help="fetch only these indicators")
    ap.add_argument("--dry-run", action="store_true", help="print, do not write")
    args = ap.parse_args(argv)
    load_dotenv(ROOT / ".env")
    client_id = os.environ.get("GUS_BDL_CLIENT_ID") or None
    bdl = Bdl(client_id, pause=0.25 if client_id else 1.2)
    print(f"GUS BDL: {'z kluczem X-ClientId' if client_id else 'bez klucza (limit 100 zapytań / 15 min)'}", file=sys.stderr)

    prev = json.loads(args.out.read_text("utf-8")) if args.out.exists() else {}
    adopters = dict(prev.get("adopters") or {})
    for key in args.only or INDICATORS:
        adopters[key] = fetch_indicator(bdl, key, INDICATORS[key], verbose=True)
        print(f"{key}: Polska {adopters[key]['poland']:,} ({adopters[key]['year']})".replace(",", " "), file=sys.stderr)
    doc = {
        "schema": "radar.adopters/v1",
        "source": "GUS, Bank Danych Lokalnych (https://bdl.stat.gov.pl), API v1",
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "note": "Liczby potencjalnych odbiorców dla wyceny (app/radar/business.py). Generowane skryptem "
                "scripts/fetch_gus_adopters.py; aplikacja nie odpytuje GUS w czasie działania.",
        "voivodeships": sorted(VOIVODESHIPS.values()),
        "adopters": adopters,
    }
    if args.dry_run:
        print(json.dumps(doc, ensure_ascii=False, indent=1)[:4000])
        return 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"zapisano {args.out} ({bdl.calls} zapytań)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
