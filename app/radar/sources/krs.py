"""Companies and spin-offs from the official KRS API (Ministry of Justice, "API Otwarte KRS"), no key, no LLM.

API: GET https://api-krs.ms.gov.pl/api/krs/OdpisAktualny/{krs}?rejestr=P&format=json (current extract of one entity).
It is free and needs no key, but it is a lookup by KRS number: there is no reverse search ("companies whose
shareholder is university X"). So the candidates come from a seed list (`app/radar/data/krs_seed.json`: special
purpose companies of universities and institutes, each with where its number was found) and, later, from KRS
numbers in the organisation registry; a company is linked to a registry organisation by what the register itself
says: a shareholder with the organisation's REGON, KRS or exact (normalized) name.

- `company_profile(doc)` keeps: name, legal form, REGON/NIP, registration date, share capital, seat voivodeship,
  main and other PKD codes, suspension, and shareholders that are legal entities. People (board members in
  dział 2, natural-person shareholders) are never read or stored.
- `KrsClient.odpis(krs)` caches each extract on disk for 30 days (`DiskCache("krs")`).
- `python -m radar.sources.krs` writes `app/radar/data/companies.json` (like adopters.json: committed, the app
  never calls KRS at request time); missing network or a failing number only skips that entry.
- `commercial_signal(...)` builds `investor.signals().commercial` from linked companies, the text cue stays as
  the fallback. Wiring it into investor.signals() waits for PR #36 (see issue #30).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import httpx

from radar.orgs import key as name_key
from radar.sources.disk_cache import DiskCache

API = "https://api-krs.ms.gov.pl/api/krs/OdpisAktualny/{krs}"
SOURCE = "KRS (api-krs.ms.gov.pl)"
DATA = Path(__file__).resolve().parents[1] / "data"
SEED_FILE = DATA / "krs_seed.json"
COMPANIES_FILE = DATA / "companies.json"
PERSON_KEYS = ("nazwisko", "imiona", "imie")


def _date(s: str | None) -> str | None:
    m = re.fullmatch(r"(\d{2})\.(\d{2})\.(\d{4})", (s or "").strip())
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else None


def _money(s) -> float | None:
    if s is None:
        return None
    t = re.sub(r"\s", "", str(s)).replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def _pkd(p: dict) -> str:
    return f"{p.get('kodDzial', '')}.{p.get('kodKlasa', '')}.{p.get('kodPodklasa', '')}".strip(".")


def _regon9(s: str | None) -> str | None:
    d = re.sub(r"\D", "", s or "")
    return d[:9] if len(d) >= 9 and d.strip("0") else None


def _krs(s: str | None) -> str | None:
    d = re.sub(r"\D", "", s or "")
    return d.zfill(10) if d.strip("0") else None


def company_profile(doc: dict, fetched_at: str | None = None) -> dict | None:
    """Plain profile of one KRS extract (legal facts only, no people)."""
    o = (doc or {}).get("odpis") or {}
    head, dane = o.get("naglowekA") or {}, o.get("dane") or {}
    d1 = dane.get("dzial1") or {}
    pod = d1.get("danePodmiotu") or {}
    if not head.get("numerKRS") or not pod.get("nazwa"):
        return None
    ids = pod.get("identyfikatory") or {}
    seat = (d1.get("siedzibaIAdres") or {}).get("siedziba") or {}
    cap = (d1.get("kapital") or {}).get("wysokoscKapitaluZakladowego") or {}
    pd = (dane.get("dzial3") or {}).get("przedmiotDzialalnosci") or {}
    main = (pd.get("przedmiotPrzewazajacejDzialalnosci") or [{}])[0]
    holders = []
    for w in d1.get("wspolnicySpzoo") or d1.get("wspolnicy") or []:
        if any(k in w for k in PERSON_KEYS) or not w.get("nazwa"):
            continue  # natural persons are personal data: never stored
        holders.append({"name": w["nazwa"], "regon": _regon9((w.get("identyfikator") or {}).get("regon")),
                        "krs": _krs((w.get("krs") or {}).get("krs")), "whole": bool(w.get("czyPosiadaCaloscUdzialow"))})
    susp = ((dane.get("dzial6") or {}).get("zawieszenieWznowienie") or [])
    suspended = bool(susp) and not susp[-1].get("dataWznowienia")
    return {
        "krs": head["numerKRS"], "name": pod["nazwa"], "legal_form": pod.get("formaPrawna"),
        "regon": _regon9(ids.get("regon")), "nip": ids.get("nip"),
        "registered": _date(head.get("dataRejestracjiWKRS")), "state_as_of": _date(head.get("stanZDnia")),
        "capital_pln": _money(cap.get("wartosc")) if (cap.get("waluta") or "PLN") == "PLN" else None,
        "voivodeship": (seat.get("wojewodztwo") or "").lower() or None, "city": (seat.get("miejscowosc") or "").title() or None,
        "pkd_main": {"code": _pkd(main), "name": (main.get("opis") or "").capitalize()} if main else None,
        "pkd_other": [_pkd(p) for p in pd.get("przedmiotPozostalejDzialalnosci") or []][:12],
        "shareholders": holders, "suspended": suspended,
        "source": SOURCE, "url": f"https://wyszukiwarka-krs.ms.gov.pl/details?krs={head['numerKRS']}",
        "fetched_at": fetched_at,
    }


class KrsClient:
    def __init__(self, cache: DiskCache | None = None, http: httpx.Client | None = None):
        self.cache = cache or DiskCache("krs", ttl_s=30 * 86400)
        self.http = http or httpx.Client(timeout=30, headers={"User-Agent": "innovation-radar/1.0 (+krs)"})

    def odpis(self, krs: str) -> dict | None:
        """Profile of one entity (register P, then S), cached on disk; None when the number is unknown."""
        num = _krs(krs)
        if not num:
            return None

        def load():
            # only the cleaned profile is cached: the raw extract lists board members (personal data)
            for reg in ("P", "S"):
                r = self.http.get(API.format(krs=num), params={"rejestr": reg, "format": "json"})
                if r.status_code == 404:
                    continue
                r.raise_for_status()
                return company_profile(r.json())
            return None

        entry = self.cache.fetch(f"profile:{num}", load)
        return {**entry["value"], "fetched_at": entry["fetched_at"]} if entry["value"] else None


def fetch_many(client: KrsClient, numbers: Iterable[str]) -> list[dict]:
    """Profiles for many numbers; network errors skip the entry (the source is optional)."""
    out = []
    for n in numbers:
        try:
            p = client.odpis(n)
        except (httpx.HTTPError, ValueError):
            continue
        if p:
            out.append(p)
    return out


def owned_by(company: dict, org: dict) -> bool:
    """True when the register lists `org` (dict with `ids` {regon, krs} and `name`/`aliases`) as a shareholder."""
    ids = org.get("ids") or {}
    regon, krs = _regon9(ids.get("regon")), _krs(ids.get("krs"))
    names = {name_key(n) for n in [org.get("name"), *(org.get("aliases") or [])] if n}
    for h in company.get("shareholders") or []:
        if (regon and h["regon"] == regon) or (krs and h["krs"] == krs) or name_key(h["name"]) in names:
            return True
    return False


def spinoffs(companies: list[dict], org: dict) -> list[dict]:
    return sorted((c for c in companies if owned_by(c, org)), key=lambda c: (c["suspended"], c.get("registered") or ""))


def load_companies(path: Path | None = None) -> list[dict]:
    try:
        doc = json.loads(Path(path or COMPANIES_FILE).read_text("utf-8"))
    except (OSError, ValueError):
        return []
    return doc.get("companies") or []


def commercial_signal(companies: list[dict], text_fallback: dict) -> dict:
    """`investor.signals().commercial` from companies linked to the organisation; text cue as the fallback."""
    active = [c for c in companies if not c["suspended"]]
    if not companies:
        return {**text_fallback, "registry": None}
    best = (active or companies)[0]
    cap = f", kapitał {round(best['capital_pln']):,} zł".replace(",", " ") if best.get("capital_pln") else ""
    route = (f"spółka celowa / spin-off w KRS: {best['name']} (od {best['registered']}{cap})" if active
             else text_fallback.get("route") or f"spółka w KRS zawieszona: {best['name']}")
    return {
        "route": route, "cue": text_fallback.get("cue"),
        "registry": {"source": SOURCE, "fetched_at": max((c.get("fetched_at") or "") for c in companies) or None,
                     "companies": [{k: c.get(k) for k in ("krs", "name", "registered", "capital_pln", "pkd_main",
                                                          "voivodeship", "suspended", "url")} for c in companies[:5]]},
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="KRS seed -> app/radar/data/companies.json")
    ap.add_argument("--seed", type=Path, default=SEED_FILE)
    ap.add_argument("--out", type=Path, default=COMPANIES_FILE)
    ap.add_argument("--allow-partial", action="store_true",
                    help="write even when some seed entries could not be fetched (default: keep the old file)")
    args = ap.parse_args(argv)
    seed = json.loads(args.seed.read_text("utf-8"))
    entries = seed.get("companies") or []
    profiles = fetch_many(KrsClient(), [e["krs"] for e in entries])
    if len(profiles) < len(entries) and not args.allow_partial:
        # fetch_many skips network errors, so a KRS outage would otherwise replace the file with an empty list
        print(f"pobrano {len(profiles)}/{len(entries)} spółek; {args.out} bez zmian (--allow-partial, by zapisać)",
              file=sys.stderr)
        return 1
    by_krs = {e["krs"]: e for e in entries}
    for p in profiles:
        p["seed_source"] = (by_krs.get(p["krs"]) or {}).get("source")
    doc = {"schema": "radar.companies/v1", "source": SOURCE,
           "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "note": "Spółki celowe i spin-offy uczelni z KRS (tylko dane podmiotu i wspólnicy będący osobami prawnymi). "
                   "Generowane: python -m radar.sources.krs; aplikacja nie odpytuje KRS w czasie działania.",
           "companies": profiles}
    args.out.write_text(json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"zapisano {args.out}: {len(profiles)}/{len(entries)} spółek", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
