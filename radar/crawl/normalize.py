"""Crawled page/document -> radar.record/v1 (same shape as the NCBR and Interreg connectors)."""
from __future__ import annotations

import hashlib
import json
import re
from urllib.parse import urlsplit

from ..pl import parse_money, parse_period, parse_voivodeships
from ..sources.ncbr import org_type_hint
from ..text import clean_text, fold
from .classify import Signals
from .extract import Page, best_title, description, modified_date, published_date
from .sites import Site

RECORD_SCHEMA = "radar.record/v1"
CONNECTOR_VERSION = "0.1.0"

ORG_PATTERNS = [
    # companies: "Nazwa Sp. z o.o." / "NAZWA S.A."
    re.compile(r"\b((?:[A-ZŁŚŻŹĆŃÓĘĄ0-9][\w&.'-]*\s+){0,5}[A-ZŁŚŻŹĆŃÓĘĄ0-9][\w&.'-]*)\s+"
               r"(sp\.\s*z\s*o\.\s*o\.|spółka z ograniczoną odpowiedzialnością|S\.A\.|sp\.\s*k\.|sp\.\s*j\.|P\.S\.A\.)", re.I),
    # public and research bodies with a proper name after the keyword
    re.compile(r"\b((?:Politechnika|Uniwersytet|Akademia|Instytut|Sieć Badawcza Łukasiewicz\s*[-–]\s*\w+|Centrum|"
               r"Park Naukowo-Technologiczny|Gmina|Miasto|Powiat|Urząd Marszałkowski|Województwo)"
               r"(?:\s+(?:[A-ZŁŚŻŹĆŃÓĘĄ][\wąćęłńóśźż-]+|im\.|w|we|i|Nauk|Technologii)){1,6})"),
]
PERIOD_RE = re.compile(r"(?:okres realizacji|termin realizacji|czas trwania projektu)\s*[:\-–]?\s*([^\n]{6,80})", re.I)
VALUE_RE = re.compile(r"(?:warto[sś][cć] (?:ca[lł]kowita )?projektu|ca[lł]kowity koszt projektu|bud[zż]et projektu)"
                      r"\s*[:\-–]?\s*([\d\s.,]+\s*(?:z[lł]|PLN|EUR|euro|mln z[lł]))", re.I)
GRANT_RE = re.compile(r"(?:dofinansowanie|wk[lł]ad (?:UE|Unii Europejskiej|funduszy europejskich)|kwota dofinansowania)"
                      r"\s*[:\-–]?\s*([\d\s.,]+\s*(?:z[lł]|PLN|EUR|euro|mln z[lł]))", re.I)
VOIV_RE = re.compile(r"wojew[oó]dztw\w*\s+([a-ząćęłńóśźż]+(?:[- ][a-ząćęłńóśźż]+)?)", re.I)


def record_id(url: str) -> str:
    parts = urlsplit(url)
    slug = re.sub(r"[^a-z0-9]+", "-", fold(parts.path.rstrip("/").rsplit("/", 1)[-1] or parts.netloc))[:60].strip("-")
    return f"{slug or 'strona'}-{hashlib.sha1(url.encode()).hexdigest()[:10]}"


def find_organizations(text: str, owner: dict, limit: int = 8) -> list[dict]:
    orgs: list[dict] = []
    seen: set[str] = set()
    if owner.get("name"):
        orgs.append({"name": owner["name"], "role": "publisher", "type_hint": owner.get("type") or org_type_hint(owner["name"]),
                     "org_id": None, "is_public": None, "source": "site_config"})
        seen.add(fold(owner["name"]))
    for pat in ORG_PATTERNS:
        for m in pat.finditer(text):
            name = clean_text(m.group(0) if pat is ORG_PATTERNS[0] else m.group(1)).strip(" ,.;:")
            key = fold(name)
            if len(name) < 6 or len(name) > 120 or key in seen:
                continue
            seen.add(key)
            orgs.append({"name": name, "role": "mentioned", "type_hint": org_type_hint(name), "org_id": None,
                         "is_public": None, "source": "text_pattern"})
            if len(orgs) >= limit:
                return orgs
    return orgs


def find_region(text: str, owner: dict) -> tuple[list[str], bool, str | None]:
    found: list[str] = []
    raw = [m.group(0) for m in VOIV_RE.finditer(text)][:10]
    for phrase in raw:
        v, _ = parse_voivodeships(phrase)
        found += [x for x in v if x not in found]
    if owner.get("voivodeship") and owner["voivodeship"] not in found:
        found.insert(0, owner["voivodeship"])
    return found, False, "; ".join(raw) or None


def build_record(site: Site, page: Page, signals: Signals, *, fetched_at: str, etag: str | None = None,
                 last_modified: str | None = None, raw_file: str | None = None) -> dict:
    title = best_title(page, site.name) or page.url
    desc = description(page)
    body = page.body_text
    paras = [b.text for b in page.blocks if not b.is_heading]
    intro = desc or (paras[0][:600] if paras else "")
    published, modified = published_date(page), modified_date(page)

    full = page.text
    orgs = find_organizations(full, site.owner)
    voivodeships, nationwide, region_raw = find_region(full, site.owner)
    m = PERIOD_RE.search(full)
    period = parse_period(m.group(1)) if m else parse_period(None)
    total = grant = cur = None
    m = VALUE_RE.search(full)
    if m:
        total, cur = parse_money(m.group(1))
    m = GRANT_RE.search(full)
    if m:
        grant, cur2 = parse_money(m.group(1))
        cur = cur or cur2
    keywords = [clean_text(k) for k in re.split(r"[,;]", page.meta.get("keywords", "") or page.meta.get("article:tag", ""))
                if clean_text(k)][:20]

    text_for_llm = "\n\n".join(x for x in (f"Tytuł: {title}", f"Źródło: {site.name} ({page.url})",
                                          f"Data publikacji: {published}" if published else "", body) if x)
    blocking, warnings = [], []
    if not best_title(page, site.name):
        blocking.append("missing_title")
    if page.kind == "pdf" and not body:
        blocking.append("pdf_text_unavailable")
    elif len(body) < 300:
        blocking.append("short_text")
    if not published:
        warnings.append("date_missing")
    if not voivodeships:
        warnings.append("region_missing")

    content = {"title": title, "body": body, "description": desc}
    content_hash = hashlib.sha256(json.dumps(content, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    return {
        "schema": RECORD_SCHEMA,
        "source": site.source,
        "source_name": f"{site.name} (strona www)",
        "record_id": record_id(page.url),
        "url": page.url,
        "list_url": site.start[0],
        "content_hash": content_hash,
        "record_type": f"web_{signals.page_type}",
        "language": page.lang or "pl",
        "title": title,
        "intro": intro,
        "text": {"body": body, "description": desc},
        "text_for_llm": text_for_llm,
        "organizations": orgs,
        "people": [],
        "funding": {"operator": None, "programme": None, "contest": None, "total_value": total, "grant_value": grant,
                    "currency": cur, "grant_share": round(grant / total, 4) if total and grant else None, "raw": {}},
        "period": period.as_dict(),
        "region": {"voivodeships": voivodeships, "nationwide": nationwide, "raw": region_raw,
                   "country": "Polska"},
        "keywords": keywords,
        "extra": {"category": site.category, "site_id": site.id, "page_type": signals.page_type,
                  "signals": signals.to_json(), "published": published, "modified": modified, "document": page.kind},
        "rights": {"licence": "unknown", "llm_may_read_fulltext": True,
                   "note": f"Publiczna strona {urlsplit(page.url).netloc}; warunki ponownego wykorzystania do potwierdzenia."},
        "quality": {"status": "needs_review" if blocking else "ok", "blocking": blocking, "warnings": warnings,
                    "narrative_chars": len(body)},
        "provenance": {"connector": f"radar.crawl/{CONNECTOR_VERSION}", "detail_fetched_at": fetched_at,
                       "etag": etag, "last_modified": last_modified, "keep_reason": signals.reason,
                       "raw_files": {"page": raw_file} if raw_file else {}},
    }
