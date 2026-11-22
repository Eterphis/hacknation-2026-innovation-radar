"""Patents and patent applications of registry organisations from EPO Open Patent Services (OPS), no LLM.

Why OPS: one free API (register at https://developers.epo.org, "Non-paying" plan, 4 GB/week) that also carries the
Polish patent office's publications (DOCDB country PL: A1 = zgłoszenie, B1 = patent, U1/Y1 = wzór użytkowy), so
UPRP data comes through the same client; EP and WO (PCT) documents of the same applicant come too.

- `EpoOps.from_env()` returns None when RADAR_EPO_OPS_KEY / RADAR_EPO_OPS_SECRET are missing: the source is
  optional and the pipeline keeps working (investor signals fall back to patent language in the text).
- `search_applicant(name)` runs one CQL query `pa="<name>"` (paged, up to `max_results`) and caches the parsed
  answer on disk for a week (`DiskCache("epo_ops")`), so a re-run costs no quota.
- `parse_search(doc)` turns the OPS JSON into plain asset dicts: publication number, kind, status, date, titles,
  Espacenet link, source and fetch date. Inventors and applicant names are NOT kept (personal data; the asset
  belongs to the organisation we queried for).
- `match_record(title, keywords, assets)` links an asset to a radar record when their titles share enough
  meaningful word stems (deterministic overlap on folded 6-letter stems, Polish and English titles).
- `ip_signal(...)` builds `investor.signals().ip` from those assets; the text-based answer stays as the fallback.

Writing assets to the `ip_assets` table and wiring `investor.signals()` to it wait for migration 0006 (after #36).
"""

from __future__ import annotations

import base64
import os
import time
from typing import Any, Iterable

import httpx

from radar.orgs import tokens
from radar.sources.disk_cache import DiskCache

OPS = "https://ops.epo.org/3.2"
SOURCE = "EPO OPS"
PAGE = 100  # OPS returns at most 100 documents per request
GENERIC_STEMS = {"sposob", "urzadz", "method", "device", "system", "zastos", "uklad", "srodek", "means",
                 "proces", "process", "wytwar", "produc", "oraz", "using", "for", "the", "and", "with", "from"}


def _list(x: Any) -> list:
    return x if isinstance(x, list) else [] if x is None else [x]


def _text(x: Any) -> str | None:
    return x.get("$") if isinstance(x, dict) else x


def status_of(country: str, kind: str) -> str:
    """granted | filed | utility_model | utility_model_filed, from the DOCDB kind code."""
    k = (kind or "").upper()
    if k.startswith("Y"):
        return "utility_model"
    if k.startswith("U"):
        return "utility_model_filed"
    if k.startswith(("B", "C")) and not (country == "WO"):
        return "granted"
    return "filed"


def parse_search(doc: dict, fetched_at: str | None = None) -> list[dict]:
    """OPS biblio search JSON -> asset dicts (no personal data)."""
    res = (((doc or {}).get("ops:world-patent-data") or {}).get("ops:biblio-search") or {}).get("ops:search-result") or {}
    out = []
    for wrap in _list(res.get("exchange-documents")):
        for ex in _list(wrap.get("exchange-document") if isinstance(wrap, dict) else None):
            country, number, kind = ex.get("@country"), ex.get("@doc-number"), ex.get("@kind")
            if not (country and number):
                continue
            bib = ex.get("bibliographic-data") or {}
            date = None
            for did in _list((bib.get("publication-reference") or {}).get("document-id")):
                if did.get("@document-id-type") == "docdb" and _text(did.get("date")):
                    d = _text(did["date"])
                    date = f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 else d
            titles = {}
            for t in _list(bib.get("invention-title")):
                if _text(t):
                    titles[(t.get("@lang") if isinstance(t, dict) else None) or "xx"] = " ".join(_text(t).split())
            pub = f"{country}{number}{kind or ''}"
            out.append({"source": SOURCE, "publication": pub, "country": country, "number": number, "kind": kind,
                        "status": status_of(country, kind), "date": date, "family_id": ex.get("@family-id"),
                        "titles": titles, "url": f"https://worldwide.espacenet.com/patent/search?q=pn%3D{pub}",
                        "fetched_at": fetched_at})
    return out


def total_count(doc: dict) -> int:
    bs = ((doc or {}).get("ops:world-patent-data") or {}).get("ops:biblio-search") or {}
    try:
        return int(bs.get("@total-result-count") or 0)
    except ValueError:
        return 0


class EpoOps:
    def __init__(self, key: str, secret: str, cache: DiskCache | None = None, http: httpx.Client | None = None,
                 max_results: int = 200):
        self.key, self.secret = key, secret
        self.cache = cache or DiskCache("epo_ops")
        self.http = http or httpx.Client(timeout=30, headers={"User-Agent": "innovation-radar/1.0 (+ip-assets)"})
        self.max_results = max_results
        self._token: tuple[str, float] | None = None

    @classmethod
    def from_env(cls, **kw) -> "EpoOps | None":
        key, secret = os.environ.get("RADAR_EPO_OPS_KEY"), os.environ.get("RADAR_EPO_OPS_SECRET")
        return cls(key, secret, **kw) if key and secret else None

    def token(self) -> str:
        if self._token and self._token[1] > time.time() + 30:
            return self._token[0]
        basic = base64.b64encode(f"{self.key}:{self.secret}".encode()).decode()
        r = self.http.post(f"{OPS}/auth/accesstoken", data={"grant_type": "client_credentials"},
                           headers={"Authorization": f"Basic {basic}"})
        r.raise_for_status()
        d = r.json()
        self._token = (d["access_token"], time.time() + int(d.get("expires_in") or 1200))
        return self._token[0]

    def _page(self, query: str, begin: int) -> dict:
        r = self.http.get(f"{OPS}/rest-services/published-data/search/biblio",
                          params={"q": query, "Range": f"{begin}-{begin + PAGE - 1}"},
                          headers={"Authorization": f"Bearer {self.token()}", "Accept": "application/json"})
        if r.status_code == 404:  # OPS answers 404 when nothing matches
            return {}
        r.raise_for_status()
        return r.json()

    def search_applicant(self, name: str) -> dict:
        """{"fetched_at", "value": [assets]} for one applicant name; cached on disk."""
        query = f'pa="{name.replace(chr(34), " ")}"'

        def load() -> list[dict]:
            assets, begin = [], 1
            while begin <= self.max_results:
                doc = self._page(query, begin)
                page = parse_search(doc)
                assets += page
                if not page or begin + PAGE > min(total_count(doc), self.max_results):
                    break
                begin += PAGE
            return assets

        entry = self.cache.fetch(query, load)
        return {"fetched_at": entry["fetched_at"],
                "value": [{**a, "fetched_at": a.get("fetched_at") or entry["fetched_at"]} for a in entry["value"]]}


def harvest_orgs(client: EpoOps | None, orgs: Iterable[tuple[str, str]]) -> dict[str, dict]:
    """org_key -> {"fetched_at", "assets"} for (key, name) pairs; {} without a client. One failing org is skipped."""
    if client is None:
        return {}
    out = {}
    for key, name in orgs:
        try:
            got = client.search_applicant(name)
        except (httpx.HTTPError, KeyError, ValueError):
            continue
        out[key] = {"fetched_at": got["fetched_at"], "assets": [{**a, "org_key": key} for a in got["value"]]}
    return out


def assets_from_harvest(rec: dict) -> dict | None:
    """The same asset shape from a harvester patent record (radar.record/v1 with a `patent` block), so the keyless
    sources (EPO Linked Data `epo_ep`, UPRP manual import `uprp_pl`) fill `ip_assets` without an OPS key.
    `organizations` keeps applicant organisations only (the harvester already splits people out)."""
    p = rec.get("patent") or {}
    if not p:
        return None
    office = p.get("office") or ("EP" if rec.get("source") == "epo_ep" else None)
    granted = bool(p.get("granted"))
    utility = "utility" in (rec.get("record_type") or "") or p.get("kind") == "utility_model"
    status = ("utility_model" if granted else "utility_model_filed") if utility else ("granted" if granted else "filed")
    number = p.get("right_number") if granted and p.get("right_number") else p.get("application_number")
    grant = p.get("grant") if isinstance(p.get("grant"), dict) else {}
    date = p.get("grant_date") or grant.get("date") or p.get("publication_date") or p.get("filing_date")
    titles = dict(p.get("titles") or {}) or ({rec.get("language") or "pl": rec["title"]} if rec.get("title") else {})
    prov = rec.get("provenance") or {}
    return {"source": rec.get("source_name") or rec.get("source"), "publication": str(number or rec.get("record_id")),
            "country": "PL" if office == "UPRP" else office, "number": number, "kind": p.get("kind"), "status": status,
            "date": date, "family_id": p.get("family"), "titles": titles, "url": rec.get("url") or rec.get("list_url"),
            "organizations": [o["name"] for o in rec.get("organizations") or [] if o.get("name")],
            "fetched_at": prov.get("detail_fetched_at") or prov.get("list_fetched_at") or prov.get("fetched_at")}


def _stems(text: str) -> set[str]:
    return {t for t in tokens(text) if len(t) >= 4 and t not in GENERIC_STEMS and not t.isdigit()}


def match_score(title: str, keywords: list[str] | None, asset: dict) -> float:
    """Overlap coefficient of meaningful stems between the record (title + keywords) and the best asset title."""
    rec = _stems(" ".join([title or "", *[str(k) for k in (keywords or [])]]))
    best = 0.0
    for t in (asset.get("titles") or {}).values():
        a = _stems(t)
        shared = rec & a
        if len(shared) >= 2:
            best = max(best, len(shared) / min(len(rec), len(a)))
    return round(best, 3)


def match_record(title: str, keywords: list[str] | None, assets: list[dict], threshold: float = 0.5) -> list[dict]:
    """Assets whose title matches the record, best first, each with its `match` score."""
    scored = [{**a, "match": s} for a in assets if (s := match_score(title, keywords, a)) >= threshold]
    return sorted(scored, key=lambda a: (-a["match"], a["status"] != "granted", a.get("date") or ""))


STRENGTH = {"granted": "strong", "utility_model": "medium", "filed": "medium", "utility_model_filed": "medium"}


def ip_signal(org_assets: list[dict], matched: list[dict], text_fallback: dict) -> dict:
    """`investor.signals().ip` from registry assets; `text_fallback` is the current text-based answer."""
    if not org_assets:
        return {**text_fallback, "registry": None}
    order = ["strong", "medium", "weak", "none"]
    from_registry = STRENGTH[matched[0]["status"]] if matched else "weak"
    strength = min(from_registry, text_fallback.get("strength", "none"), key=order.index)
    granted = [a for a in org_assets if a["status"] in ("granted", "utility_model")]
    return {
        "strength": strength,
        "in_text": text_fallback.get("in_text"),
        "org_patents": len(org_assets),
        "examples": [{"publication": a["publication"], "title": next(iter(a["titles"].values()), None), "status": a["status"],
                      "date": a["date"], "url": a["url"]} for a in (matched or granted or org_assets)[:3]],
        "registry": {"source": SOURCE, "fetched_at": max((a.get("fetched_at") or "") for a in org_assets) or None,
                     "granted": len(granted), "filed": len(org_assets) - len(granted),
                     "matched": [{"publication": a["publication"], "status": a["status"], "match": a["match"],
                                  "url": a["url"]} for a in matched[:5]]},
    }
