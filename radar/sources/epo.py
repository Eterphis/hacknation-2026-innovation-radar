"""European patent applications with a Polish applicant (EPO Register data via EPO Linked Data).

EPO Register's own API (OPS) needs a registered key. The same register data is published by the EPO
without a key as Linked Data:
  * SPARQL endpoint https://data.epo.org/linked-data/query  - bibliographic data (applicants with
    country, inventors, titles, CPC/IPC, filing and publication dates, family, PCT, priorities);
  * publication documents (XML)                             - abstract, claims, description and the
    applicant's full address; Euro-PCT publications carry bibliography only (the abstract is in WO).

One record per application (A1/A2 and a later B1 describe one invention); the link points to the
application's page in EPO Register.

Run:  python -X utf8 -m radar.sources.epo --since 2020-01-01 --out data/normalized/epo.jsonl
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator
from urllib.parse import urlencode

from .. import RECORD_SCHEMA
from ..http import FetchError, Response, fetch
from ..text import clean_text, fold
from .ncbr import org_type_hint

SOURCE = "epo_ep"
SOURCE_NAME = "EPO – zgłoszenia patentów europejskich (EPO Register / Linked Data)"
CONNECTOR_VERSION = "0.1.0"
CATEGORY = "nauka"
SPARQL_URL = "https://data.epo.org/linked-data/query"
REGISTER_URL = "https://register.epo.org/application?number=EP{number}"
PAT = "http://data.epo.org/linked-data/def/patent/"
PREFIXES = ("PREFIX pat: <http://data.epo.org/linked-data/def/patent/> "
            "PREFIX vcard: <http://www.w3.org/2006/vcard/ns#> "
            "PREFIX xsd: <http://www.w3.org/2001/XMLSchema#> ")
FIRST_KINDS = ("A1", "A2")  # first publication of an application (with / without search report)
BATCH = 40
PAGE = 1000
DESCRIPTION_CHARS = 2500


# --- SPARQL ---------------------------------------------------------------------
def list_query(country: str, since: str, until: str | None, limit: int, offset: int) -> str:
    kinds = ", ".join(f"pat:publicationKind_{k}" for k in FIRST_KINDS)
    until_f = f' && ?d < "{until}"^^xsd:date' if until else ""
    return PREFIXES + f"""
SELECT DISTINCT ?pub ?app ?kind ?num ?d ?pct WHERE {{
  ?pub pat:applicantVC ?vc . ?vc vcard:hasAddress ?a . ?a pat:countryCode "{country}" .
  ?pub pat:publicationKind ?kind . FILTER(?kind IN ({kinds}))
  ?pub pat:publicationDate ?d . FILTER(?d >= "{since}"^^xsd:date{until_f})
  ?pub pat:application ?app . ?pub pat:publicationNumber ?num .
  OPTIONAL {{ ?pub pat:internationalApplication ?pct }}
}} ORDER BY ?d ?pub LIMIT {limit} OFFSET {offset}"""


def _values(var: str, uris: list[str]) -> str:
    return f"VALUES ?{var} {{ " + " ".join(f"<{u}>" for u in uris) + " }"


def detail_queries(pubs: list[str], apps: list[str]) -> dict[str, str]:
    return {
        "titles": PREFIXES + f"SELECT ?pub ?t (lang(?t) AS ?l) WHERE {{ {_values('pub', pubs)} ?pub pat:titleOfInvention ?t }}",
        "parties": PREFIXES + f"""SELECT ?pub ?role ?name ?cc WHERE {{ {_values('pub', pubs)}
            {{ ?pub pat:applicantVC ?vc BIND("applicant" AS ?role) }} UNION {{ ?pub pat:inventorVC ?vc BIND("inventor" AS ?role) }}
            ?vc vcard:fn ?name . OPTIONAL {{ ?vc vcard:hasAddress ?a . ?a pat:countryCode ?cc }} }}""",
        "reps": PREFIXES + f"SELECT ?pub ?rep WHERE {{ {_values('pub', pubs)} ?pub pat:representation ?rep }}",
        "priorities": PREFIXES + f"SELECT ?pub ?prio WHERE {{ {_values('pub', pubs)} ?pub pat:priority ?prio }}",
        "apps": PREFIXES + f"""SELECT ?app ?num ?orig ?filed ?fam WHERE {{ {_values('app', apps)}
            OPTIONAL {{ ?app pat:applicationNumber ?num }} OPTIONAL {{ ?app pat:applicationNumberOriginal ?orig }}
            OPTIONAL {{ ?app pat:filingDate ?filed }} OPTIONAL {{ ?app pat:familyMemberOf ?fam }} }}""",
        "cpc": PREFIXES + f"SELECT ?app ?c WHERE {{ {_values('app', apps)} ?app pat:classificationCPCInventive ?c }}",
        "ipc": PREFIXES + f"SELECT ?pub ?c WHERE {{ {_values('pub', pubs)} ?pub pat:classificationIPCInventive ?c }}",
        "grants": PREFIXES + f"""SELECT ?app ?g ?gnum ?gd WHERE {{ {_values('app', apps)}
            ?g pat:application ?app . ?g pat:publicationKind pat:publicationKind_B1 .
            ?g pat:publicationNumber ?gnum . ?g pat:publicationDate ?gd }}""",
    }


def bindings(payload: dict) -> list[dict]:
    return [{k: v["value"] for k, v in b.items()} for b in payload["results"]["bindings"]]


def code(uri: str) -> str:
    """http://data.epo.org/linked-data/def/cpc/B67C7-0026 -> B67C 7/0026 (CPC/IPC notation)."""
    c = uri.rsplit("/", 1)[-1]
    m = re.fullmatch(r"([A-H]\d{2}[A-Z])(\d+)-(\d+)", c)
    return f"{m.group(1)} {m.group(2)}/{m.group(3)}" if m else c


# --- document XML ---------------------------------------------------------------
def _strip(fragment: str) -> str:
    fragment = re.sub(r"<(br|p|li|heading)\b[^>]*>", "\n", fragment)
    return clean_text(html.unescape(re.sub(r"<[^>]+>", " ", fragment)))


def parse_document(xml: str) -> dict:
    """Abstract, first claim, start of description and applicants' addresses from an EP document."""
    xml = re.sub(r"<!--.*?-->", " ", xml, flags=re.S)

    def block(tag: str) -> str | None:
        m = re.search(rf"<{tag}\b[^>]*>(.*?)</{tag}>", xml, re.S)
        return m.group(1) if m else None

    abstract = block("abstract")
    claims = block("claims")
    first_claim = None
    if claims:
        m = re.search(r"<claim\b[^>]*>(.*?)</claim>", claims, re.S)
        first_claim = _strip(m.group(1)) if m else None
    description = block("description")
    desc_text = _strip(description) if description else None
    if desc_text and len(desc_text) > DESCRIPTION_CHARS:
        desc_text = desc_text[:DESCRIPTION_CHARS].rsplit(" ", 1)[0] + " …"
    applicants = []
    for b in re.findall(r"<B711>(.*?)</B711>", xml, re.S):
        get = lambda t: (_strip(m.group(1)) if (m := re.search(rf"<{t}>(.*?)</{t}>", b, re.S)) else None)  # noqa: E731
        city = get("city") or ""
        pm = re.match(r"(\d{2}-\d{3})\s+(.+)", city)
        applicants.append({"name": get("snm"), "street": get("str"), "postal_code": pm.group(1) if pm else None,
                           "city": pm.group(2) if pm else (city or None), "country": get("ctry")})
    lang = (re.search(r'<ep-patent-document[^>]*\blang="(\w+)"', xml) or [None, None])[1]
    return {"abstract": _strip(abstract) if abstract else None, "first_claim": first_claim,
            "description": desc_text, "applicants": applicants, "language": lang}


# --- raw store --------------------------------------------------------------------
class RawStore:
    """SPARQL answers and document XML on disk, keyed by a hash of the query or the document id."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def _q(self, query: str) -> Path:
        return self.root / "sparql" / f"{hashlib.sha1(query.encode()).hexdigest()[:16]}.json"

    def get_query(self, query: str) -> dict | None:
        p = self._q(query)
        return json.loads(p.read_text("utf-8")) if p.exists() else None

    def put_query(self, query: str, payload: dict, fetched_at: str) -> None:
        p = self._q(query)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"query": query, "fetched_at": fetched_at, "payload": payload}, ensure_ascii=False), "utf-8")

    def doc_path(self, pub_id: str) -> Path:
        return self.root / "docs" / f"{pub_id}.xml"


# --- normalization ----------------------------------------------------------------
def _pub_id(pub_uri: str) -> str:
    """.../publication/EP/4761999/A1/- -> EP4761999A1"""
    parts = pub_uri.rstrip("/-").rstrip("/").split("/")
    return "".join(parts[-3:])


def _name(epo_name: str) -> str:
    """Inventor 'NOWACKI, Tomasz' or 'Suwalski, Piotr' -> 'Tomasz Nowacki' / 'Piotr Suwalski'."""
    m = re.fullmatch(r"\s*([^,]+?),\s*([^,]+?)\s*", epo_name)
    if not m:
        return epo_name
    last, first = m.groups()
    if last.isupper():
        last = "-".join(part.capitalize() for part in last.lower().split("-"))
    return f"{first} {last}"


def build_record(app: dict, *, country: str, today_fetch: str | None) -> dict:
    """`app`: merged data of one application (see harvest)."""
    number = re.sub(r"[^0-9]", "", app["app_number"].split(".")[0])  # application number without check digit
    titles = app["titles"]
    title = titles.get("en") or titles.get("pl") or next(iter(titles.values()), "")
    doc = app.get("doc") or {}
    applicants = []
    doc_addr = {fold(a["name"] or ""): a for a in doc.get("applicants", [])}
    for name, cc in app["applicants"]:
        addr = doc_addr.get(fold(name))
        applicants.append({"name": name, "role": "applicant", "country": cc, "type_hint": org_type_hint(name),
                           "location": ({k: addr.get(k) for k in ("street", "postal_code", "city", "country")} if addr else {"country": cc}),
                           "org_id": None, "is_public": None})
    inventors = [{"name": _name(n), "role": "inventor", "country": cc, "source_text": n} for n, cc in app["inventors"]]
    pl_cities = [a["location"].get("city") for a in applicants if a["country"] == country and a["location"].get("city")]

    text = {"abstract": doc.get("abstract"), "first_claim": doc.get("first_claim"),
            "description": doc.get("description"), "other": []}
    cpc = sorted(set(app["cpc"]))
    text_for_llm = "\n\n".join(x for x in [
        f"Tytuł: {title}",
        f"Abstrakt:\n{text['abstract']}" if text["abstract"] else "",
        f"Zastrzeżenie 1:\n{text['first_claim']}" if text["first_claim"] else "",
        f"Klasy CPC: {', '.join(cpc)}" if cpc else "",
    ] if x)

    blocking, warnings = [], []
    if not title:
        blocking.append("missing_title")
    if app.get("doc_error"):
        warnings.append(f"document_not_fetched: {app['doc_error']}")
    elif app.get("doc") is None:
        warnings.append("document_not_fetched")
    elif not text["abstract"]:
        warnings.append("abstract_not_in_ep_publication" + (" (Euro-PCT: abstract in WO publication)" if app["pct"] else ""))
    granted = bool(app["grant"])
    content = {k: app[k] for k in ("app_number", "titles", "applicants", "inventors", "cpc", "ipc", "grant", "pubs")}
    content["text"] = text
    return {
        "schema": RECORD_SCHEMA,
        "source": SOURCE,
        "source_name": SOURCE_NAME,
        "record_id": f"ep-{number}",
        "url": REGISTER_URL.format(number=number),
        "list_url": SPARQL_URL,
        "content_hash": hashlib.sha256(json.dumps(content, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
        "record_type": "patent_application",
        "language": doc.get("language") or "en",
        "title": title,
        "intro": None,
        "text": text,
        "text_for_llm": text_for_llm,
        "organizations": applicants,
        "people": inventors,
        "funding": {},
        "patent": {
            "application_number": f"EP{number}",
            "application_number_original": app.get("app_number_original"),
            "filing_date": app["filed"],
            "publications": app["pubs"],
            "first_publication": app["pubs"][0] if app["pubs"] else None,
            "granted": granted,
            "grant": app["grant"],
            "pct_application": app["pct"],
            "priorities": sorted(set(app["priorities"])),
            "family": app["family"],
            "cpc": cpc,
            "ipc": sorted(set(app["ipc"])),
            "titles": titles,
        },
        "period": {"start": app["filed"], "end": None, "precision": "day" if app["filed"] else None,
                   "status": "granted" if granted else "pending_or_unknown", "ongoing": False,
                   "raw": f"zgłoszenie {app['filed'] or '?'}" + (f", udzielenie {app['grant']['date']}" if granted else "")},
        "region": {"voivodeships": [], "nationwide": False, "raw": ", ".join(dict.fromkeys(pl_cities)) or None, "country": country},
        "keywords": [],
        "extra": {"category": CATEGORY},
        "rights": {"licence": "EPO Linked Data / publication server – dane publiczne EPO",
                   "llm_may_read_fulltext": True,
                   "note": "Dane bibliograficzne i publikacje patentowe udostępniane przez EPO; warunki ponownego wykorzystania do potwierdzenia."},
        "quality": {"status": "needs_review" if blocking else "ok", "blocking": blocking, "warnings": warnings,
                    "narrative_chars": len(text["abstract"] or "")},
        "provenance": {
            "connector": f"radar.sources.epo/{CONNECTOR_VERSION}",
            "list_fetched_at": app.get("list_fetched_at"),
            "detail_fetched_at": app.get("doc_fetched_at") or today_fetch,
            "sparql_endpoint": SPARQL_URL,
            "source_documents": [p["xml"] for p in app["pubs"] if p.get("xml")],
            "raw_files": app.get("raw_files", {}),
        },
    }


# --- harvest ------------------------------------------------------------------------
@dataclass
class HarvestStats:
    publications: int = 0
    applications: int = 0
    docs_fetched: int = 0
    docs_cached: int = 0
    doc_errors: int = 0
    with_abstract: int = 0
    granted: int = 0
    queries: int = 0
    status: Counter = field(default_factory=Counter)

    def summary(self) -> str:
        return (f"first publications: {self.publications}, applications (records): {self.applications}, granted: {self.granted}\n"
                f"documents: fetched {self.docs_fetched}, cached {self.docs_cached}, errors {self.doc_errors}; "
                f"with abstract: {self.with_abstract}\nSPARQL queries: {self.queries}\n"
                "quality: " + ", ".join(f"{k}={v}" for k, v in self.status.most_common()))


class Harvester:
    def __init__(self, store: RawStore, fetcher: Callable[..., Response] = fetch, offline: bool = False,
                 refresh: bool = False, delay: float = 0.5, stats: HarvestStats | None = None) -> None:
        self.store, self.fetcher, self.offline, self.refresh, self.delay = store, fetcher, offline, refresh, delay
        self.stats = stats or HarvestStats()
        self._last = 0.0

    def _pause(self) -> None:
        wait = self.delay - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()

    def sparql(self, query: str) -> tuple[list[dict], str | None]:
        cached = None if self.refresh else self.store.get_query(query)
        if cached:
            return bindings(cached["payload"]), cached["fetched_at"]
        if self.offline:
            raise FileNotFoundError("brak zapisanej odpowiedzi SPARQL (uruchom raz bez --offline)")
        self._pause()
        resp = self.fetcher(SPARQL_URL + "?" + urlencode({"query": query}), timeout=120,
                            accept="application/sparql-results+json")
        payload = json.loads(resp.text)
        self.store.put_query(query, payload, resp.fetched_at)
        self.stats.queries += 1
        return bindings(payload), resp.fetched_at

    def document(self, pub_id: str, url: str) -> tuple[dict | None, str | None, str | None]:
        path = self.store.doc_path(pub_id)
        if path.exists() and not self.refresh:
            self.stats.docs_cached += 1
            return parse_document(path.read_text("utf-8")), None, None
        if self.offline:
            return None, None, None
        self._pause()
        try:
            resp = self.fetcher(url, timeout=60, accept="application/xml,text/xml")
        except FetchError as e:
            self.stats.doc_errors += 1
            return None, None, str(e)
        if "<ep-patent-document" not in resp.text:
            self.stats.doc_errors += 1
            return None, None, "response is not an EP patent document"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(resp.text, "utf-8")
        self.stats.docs_fetched += 1
        return parse_document(resp.text), resp.fetched_at, None

    def run(self, country: str = "PL", since: str = "2020-01-01", until: str | None = None,
            limit: int | None = None, with_docs: bool = True) -> Iterator[dict]:
        # 1. first publications (A1/A2), paged
        rows, offset, list_fetched = [], 0, None
        while True:
            page, fetched = self.sparql(list_query(country, since, until, PAGE, offset))
            list_fetched = list_fetched or fetched
            rows += page
            if len(page) < PAGE or (limit and len(rows) >= limit * 2):
                break
            offset += PAGE
        by_app: dict[str, dict] = {}
        for r in rows:
            a = by_app.setdefault(r["app"], {"pubs": {}, "pct": r.get("pct")})
            a["pubs"][r["pub"]] = {"kind": r["kind"].rsplit("_", 1)[-1], "number": r["num"], "date": r["d"]}
            a["pct"] = a["pct"] or r.get("pct")
        self.stats.publications = len(rows)
        apps = list(by_app)[: limit] if limit else list(by_app)

        # 2. details in batches
        for i in range(0, len(apps), BATCH):
            chunk = apps[i: i + BATCH]
            pubs = [p for a in chunk for p in by_app[a]["pubs"]]
            res = {name: self.sparql(q)[0] for name, q in detail_queries(pubs, chunk).items()}
            pub_app = {p: a for a in chunk for p in by_app[a]["pubs"]}
            per = defaultdict(lambda: {"titles": {}, "applicants": [], "inventors": [], "cpc": [], "ipc": [],
                                       "priorities": [], "reps": {}, "grant": None, "filed": None, "family": None,
                                       "app_number": ""})
            for r in res["titles"]:
                per[pub_app[r["pub"]]]["titles"].setdefault(r.get("l") or "und", clean_text(r["t"]))
            for r in res["parties"]:
                key = "applicants" if r["role"] == "applicant" else "inventors"
                item = (clean_text(r["name"]), r.get("cc"))
                if item not in per[pub_app[r["pub"]]][key]:
                    per[pub_app[r["pub"]]][key].append(item)
            for r in res["reps"]:
                per[pub_app[r["pub"]]]["reps"].setdefault(r["pub"], []).append(r["rep"])
            for r in res["priorities"]:
                per[pub_app[r["pub"]]]["priorities"].append(r["prio"].split("/application/", 1)[-1].replace("/", ""))
            for r in res["apps"]:
                d = per[r["app"]]
                d["app_number"] = r.get("num") or d["app_number"]
                d["app_number_original"] = r.get("orig") or d.get("app_number_original")
                d["filed"] = r.get("filed") or d["filed"]
                d["family"] = (r.get("fam") or "").rsplit("/", 1)[-1] or d["family"]
            for r in res["cpc"]:
                per[r["app"]]["cpc"].append(code(r["c"]))
            for r in res["ipc"]:
                per[pub_app[r["pub"]]]["ipc"].append(code(r["c"]))
            for r in res["grants"]:
                per[r["app"]]["grant"] = {"publication": f"EP{r['gnum']}B1", "date": r["gd"]}

            for a in chunk:
                d = per[a]
                d["app_number"] = d["app_number"] or a.rsplit("/", 1)[-1]
                pubs_sorted = sorted(by_app[a]["pubs"].items(), key=lambda kv: kv[1]["date"])
                d["pubs"] = []
                for uri, p in pubs_sorted:
                    reps = d["reps"].get(uri, [])
                    d["pubs"].append({"id": _pub_id(uri), **p,
                                      "xml": next((u for u in reps if u.endswith(".xml")), None),
                                      "html": next((u for u in reps if u.endswith(".html")), None),
                                      "pdf": next((u for u in reps if u.endswith(".pdf")), None)})
                d["pct"] = (by_app[a]["pct"] or "").split("/application/", 1)[-1].replace("/", "") or None
                d["list_fetched_at"] = list_fetched
                d["doc"] = None
                first = d["pubs"][0] if d["pubs"] else None
                if with_docs and first and first.get("xml"):
                    doc, fetched_at, err = self.document(first["id"], first["xml"])
                    d["doc"], d["doc_fetched_at"], d["doc_error"] = doc, fetched_at, err
                    if doc is not None:
                        d["raw_files"] = {"source_document": str(self.store.doc_path(first["id"]))}
                rec = build_record(d, country=country, today_fetch=list_fetched)
                self.stats.applications += 1
                self.stats.granted += int(rec["patent"]["granted"])
                self.stats.with_abstract += int(bool(rec["text"]["abstract"]))
                self.stats.status[rec["quality"]["status"]] += 1
                yield rec


CSV_COLUMNS = ["record_id", "title", "applicants", "inventors", "filing_date", "first_publication", "granted",
               "cpc", "has_abstract", "url"]


def _csv_row(r: dict) -> dict:
    p = r["patent"]
    return {"record_id": r["record_id"], "title": r["title"],
            "applicants": "; ".join(o["name"] for o in r["organizations"]),
            "inventors": "; ".join(x["name"] for x in r["people"]), "filing_date": p["filing_date"],
            "first_publication": (p["first_publication"] or {}).get("id"), "granted": p["granted"],
            "cpc": ", ".join(p["cpc"][:5]), "has_abstract": bool(r["text"]["abstract"]), "url": r["url"]}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--country", default="PL", help="applicant country code (default PL)")
    ap.add_argument("--since", default="2020-01-01", help="first publication date from (YYYY-MM-DD)")
    ap.add_argument("--until", default=None, help="first publication date before (YYYY-MM-DD)")
    ap.add_argument("--limit", type=int, default=None, help="stop after N applications")
    ap.add_argument("--no-docs", action="store_true", help="skip document XML (no abstracts, much faster)")
    ap.add_argument("--delay", type=float, default=0.5, help="seconds between requests")
    ap.add_argument("--out", default="data/normalized/epo.jsonl")
    ap.add_argument("--csv", default=None)
    ap.add_argument("--raw-dir", default="data/raw/epo")
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args(argv)

    stats = HarvestStats()
    h = Harvester(RawStore(Path(args.raw_dir)), offline=args.offline, refresh=args.refresh, delay=args.delay, stats=stats)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    rows = []
    with tmp.open("w", encoding="utf-8") as fh:
        for rec in h.run(args.country, args.since, args.until, args.limit, with_docs=not args.no_docs):
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            rows.append(_csv_row(rec))
            if stats.applications % 100 == 0:
                print(f"... {stats.applications} applications", file=sys.stderr)
    tmp.replace(out)
    if args.csv:
        with open(args.csv, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=CSV_COLUMNS, delimiter=";")
            w.writeheader()
            w.writerows(rows)
    print(stats.summary(), file=sys.stderr)
    print(f"wrote {stats.applications} records to {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
