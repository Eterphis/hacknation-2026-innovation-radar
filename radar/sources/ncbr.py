"""NCBR "Wyszukiwarka sukcesów beneficjentów" -> normalized records.

Two page types on gov.pl:
  * list page: one <details> card per project (title, beneficiary, programme, contest, amounts,
    period, region, keywords, link "Dowiedz się więcej");
  * detail page: <article> with h2 title, p.intro teaser and <h3> sections
    ("Jaki problem rozwiązuje nasz projekt?", "Kto korzysta/skorzysta z wyników projektu?", ...).
Region and keywords exist only on the list card, the narrative only on the detail page,
so a record is the merge of both.

Run:  python -m radar.sources.ncbr --out data/normalized/ncbr.jsonl
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable, Iterator
from urllib.parse import urljoin

from .. import RECORD_SCHEMA
from ..http import FetchError, Response, fetch
from ..pl import parse_money, parse_period, parse_voivodeships
from ..text import Block, clean_text, fold, html_blocks, slice_element

SOURCE = "ncbr_sukcesy"
SOURCE_NAME = "NCBR – Wyszukiwarka sukcesów beneficjentów"
CONNECTOR_VERSION = "0.1.0"
BASE_URL = "https://www.gov.pl"
LIST_URL = "https://www.gov.pl/web/ncbr/wyszukiwarka-sukcesow-beneficjentow"
DETAIL_PREFIX = "/web/ncbr/"
MIN_TEXT_CHARS = 200

# --- labels ------------------------------------------------------------------
# Metadata labels: matched as the whole label, and also found inline when a card crams
# "Wartość projektu 4 522 020,00 zł Wartość dofinansowania ..." into one bold paragraph.
META_LABELS: list[tuple[str, str]] = [
    ("title", r"tytul projektu"),
    ("beneficiaries", r"nazwa beneficjenta(?:\s*/\s*beneficjentow)?"),
    ("partners", r"partnerzy projektu"),
    ("programme", r"nazwa programu"),
    ("contest", r"konkurs"),
    ("total_value", r"wartosc projektu"),
    ("grant_value", r"wartosc dofinansowania"),
    ("period", r"okres realizacji(?: projektu)?"),
    ("region", r"region"),
    ("keywords", r"slowa kluczowe"),
    ("thesis_title", r"tytul rozprawy doktorskiej"),
]
# Narrative section headings (detail page); matched by prefix, wording varies between pages.
SECTION_PREFIXES: list[tuple[str, tuple[str, ...]]] = [
    ("team", ("poznajcie nasz zespol", "poznaj nasz zespol", "nasz zespol", "zespol")),
    ("result", ("zobacz", "efekt naszej pracy", "efekty projektu", "rezultat")),
    ("problem", ("jaki problem",)),
    ("users", ("kto korzysta", "kto skorzysta")),
    ("challenges", ("co bylo dla nas najwiekszym wyzwaniem", "najwiekszym wyzwaniem", "najwieksze wyzwanie")),
    ("advice", ("nasza rada",)),
    # second page template (commercialisation interview), seen on a handful of pages
    ("market_readiness", ("czy udalo sie panstwu stworzyc",)),
    ("commercialization", ("jak wygladala sciezka komercjalizacji",)),
    ("commercialization_barriers", ("czy napotkali panstwo na trudnosci",)),
    ("ip", ("jak uregulowano kwestie wlasnosci intelektualnej",)),
    ("_ignore", ("wideo", "film")),
]
NARRATIVE_KEYS = ("problem", "result", "users", "challenges", "advice",
                  "market_readiness", "commercialization", "commercialization_barriers", "ip")
NARRATIVE_HEADINGS = {
    "intro": "Zajawka",
    "problem": "Jaki problem rozwiązuje projekt",
    "result": "Efekt pracy",
    "users": "Kto korzysta / skorzysta z wyników",
    "challenges": "Największe wyzwania",
    "advice": "Rada dla innych wnioskodawców",
    "market_readiness": "Czy powstał produkt lub technologia gotowa do wykorzystania na rynku",
    "commercialization": "Ścieżka komercjalizacji",
    "commercialization_barriers": "Trudności w komercjalizacji",
    "ip": "Własność intelektualna",
}
_INLINE_RE = re.compile(r"(?<![a-z])(?:" + "|".join(f"(?P<{k}>{p})" for k, p in META_LABELS) + r")\s*:?")


def _fold_aligned(text: str) -> str:
    """fold() that keeps one output char per input char, so regex offsets map back to `text`."""
    out = []
    for ch in text:
        f = fold(ch) if ch.strip() else " "
        out.append(f[0] if len(f) == 1 else (f[:1] or " "))
    return "".join(out)


def label_key(text: str) -> str | None:
    f = fold(text).strip(" :?.")
    if not f or len(f) > 120:
        return None
    for key, pat in META_LABELS:
        if re.fullmatch(pat, f):
            return key
    for key, prefixes in SECTION_PREFIXES:
        if f.startswith(prefixes):
            return key
    return None


def split_inline(text: str) -> list[tuple[str, str]] | None:
    """'Wartość projektu 1 325 221,00 zł Wartość dofinansowania 1 148 750,00 zł Region:'
    -> [('total_value','1 325 221,00 zł'), ('grant_value','1 148 750,00 zł'), ('region','')]."""
    f = _fold_aligned(text)
    matches = list(_INLINE_RE.finditer(f))
    if not matches or matches[0].start() > 3:
        return None
    pairs = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        value = text[m.end():end].strip(" :.–-\n")
        pairs.append((m.lastgroup or "", value))
    return pairs


# --- parsing -----------------------------------------------------------------
@dataclass
class Parsed:
    """Label -> values from one card or one detail page. Unknown headings land in `other`."""

    fields: dict[str, list[str]] = field(default_factory=dict)
    other: list[dict[str, str]] = field(default_factory=list)
    title: str | None = None
    intro: str | None = None
    detail_url: str | None = None

    def add(self, key: str, value: str) -> None:
        if value:
            self.fields.setdefault(key, []).append(value)

    def to_json(self) -> dict:
        return {"fields": self.fields, "other": self.other, "title": self.title, "intro": self.intro,
                "detail_url": self.detail_url}


def _is_detail_url(href: str | None) -> bool:
    if not href:
        return False
    path = href.replace(BASE_URL, "")
    return path.startswith(DETAIL_PREFIX) and not path.rstrip("/").endswith("wyszukiwarka-sukcesow-beneficjentow")


def _walk(blocks: list[Block], parsed: Parsed) -> Parsed:
    current: str | None = None  # key of the label that owns the following text
    other_heading: str | None = None
    for b in blocks:
        if b.kind == "link":
            if _is_detail_url(b.href) and parsed.detail_url is None:
                parsed.detail_url = urljoin(BASE_URL, b.href)
            continue
        if b.kind not in ("text", "heading"):
            continue
        if b.tag == "summary":
            parsed.title = parsed.title or b.text
            continue
        if b.tag == "h2" and parsed.title is None:
            parsed.title = b.text
            continue
        if "intro" in b.classes:
            parsed.intro = b.text
            continue
        if fold(b.text).startswith("dowiedz sie wiecej"):
            continue
        if b.kind == "heading" or b.strong_only:
            key = label_key(b.text)
            if key:
                current, other_heading = key, None
                continue
            pairs = split_inline(b.text)
            if pairs:
                for key, value in pairs:
                    parsed.add(key, value)
                last_key, last_val = pairs[-1]
                current, other_heading = (last_key if not last_val else None), None
                continue
            if b.kind == "heading":
                current, other_heading = None, b.text
                continue
        if current == "_ignore":
            continue
        if current:
            parsed.add(current, b.text)
        else:
            parsed.other.append({"heading": other_heading or "", "text": b.text})
    return parsed


def parse_list(html: str) -> list[Parsed]:
    """All cards from the list page, in page order."""
    scope = slice_element(html, "article") or html
    cards: list[Parsed] = []
    group: list[Block] | None = None
    for b in html_blocks(scope, group_tag="details"):
        if b.kind == "group_start":
            group = []
        elif b.kind == "group_end":
            if group is not None:
                cards.append(_walk(group, Parsed()))
            group = None
        elif group is not None:
            group.append(b)
    return cards


def parse_detail(html: str) -> Parsed | None:
    article = slice_element(html, "article")
    if not article:
        return None
    return _walk(html_blocks(article), Parsed())


# --- normalization helpers ---------------------------------------------------
ORG_TYPE_HINTS: list[tuple[str, tuple[str, ...]]] = [
    ("university", ("uniwersytet", "politechnika", "akademia", "uczelnia", "wyzsza szkola", "collegium", "szkola glowna")),
    ("research_institute", ("instytut", "lukasiewicz", "polska akademia nauk", " pan ", "centrum badan", "narodowe centrum")),
    ("local_government", ("gmina", "miasto ", "urzad miasta", "urzad gminy", "starostwo", "powiat", "wojewodztwo", "marszalkowski")),
    ("public_administration", ("ministerstw", "minister ", "komend", "policj", "straz ", "urzad", "inspektorat", "glowny inspektor")),
    ("school", ("szkola", "zespol szkol", "liceum", "technikum", "przedszkole")),
    ("hospital", ("szpital", "klinika")),
    ("ngo", ("fundacja", "stowarzyszenie")),
    ("company", ("sp. z o.o", "spolka", "s.a.", " sa ", "sp.k", "sp. k.", "s.c.", "ltd", "gmbh", "inc.", "p.s.a")),
    ("other_org", ("centrum", "osrodek", "konsorcjum", "laboratorium", "park ", "klaster", "agencja", "izba", "zaklad", "przedsiebiorstwo", "siec badawcza")),
]
SUBUNIT_WORDS = ("wydzial", "katedra", "zaklad ", "instytut ", "pracownia", "filia", "oddzial")
TITLE_RE = re.compile(
    r"^(?:(?:prof|dr|hab|in[zż]|mgr|lic|lek|med|n|ks|doc|arch|wet)\.?(?:\s+|$))+", re.I
)
ROLE_WORDS = ("kierownik", "kierowniczka", "koordynator", "koordynatorka", "lider", "liderka", "zespol",
              "czlonk", "wykonawc", "opiekun", "promotor", "doktorant", "autor", "kierownictwo", "badacz")


def org_type_hint(name: str) -> str | None:
    f = " " + fold(name) + " "
    for kind, words in ORG_TYPE_HINTS:
        if any(w in f for w in words):
            return kind
    return None


def _looks_like_person(text: str) -> bool:
    t = TITLE_RE.sub("", text.strip()).strip(" ,.")
    if not t or re.search(r"\d", t) or org_type_hint(t):
        return False
    tokens = t.split()
    return 2 <= len(tokens) <= 4 and all(re.fullmatch(r"[A-ZŁŚŻŹĆŃÓĘĄ][\w'’\-]+\.?", tok) for tok in tokens)


def parse_parties(raw: str | None, role: str) -> tuple[list[dict], list[dict]]:
    """'Marek Adam Napierała, Polskie Centrum Fotoniki i Światłowodów'
    -> orgs [{name:'Polskie Centrum ...', role}], people [{name:'Marek Adam Napierała', role}]."""
    orgs: list[dict] = []
    people: list[dict] = []
    if not raw:
        return orgs, people
    chunks = [c for c in re.split(r";|\n|\s+oraz\s+|\s+\|\s+", raw) if c.strip()]
    for chunk in chunks:
        pieces = [p.strip(" .") for p in chunk.split(",") if p.strip(" .")]
        merged: list[str] = []
        for p in pieces:
            fp = fold(p)
            is_tail = merged and not _looks_like_person(p) and (
                not org_type_hint(p) or fp.startswith(SUBUNIT_WORDS) or len(p) < 4
            )
            if is_tail:
                merged[-1] = f"{merged[-1]}, {p}"
            else:
                merged.append(p)
        for name in merged:
            if _looks_like_person(name):
                people.append({"name": TITLE_RE.sub("", name).strip(), "role": role, "source_text": name})
            else:
                orgs.append({"name": name, "role": role, "type_hint": org_type_hint(name),
                             "org_id": None, "is_public": None})
    return orgs, people


def parse_team(lines: list[str]) -> list[dict]:
    """Figure captions like 'Kierownik projektu - dr inż. Marek Napierała'."""
    people: list[dict] = []
    for text in lines:
        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue
            m = re.match(r"(.+?)\s+[-–—:]\s+(.+)", line) or re.match(r"(.+?):\s*(.+)", line)
            role, names = None, line
            if m:
                left, right = m.group(1), m.group(2)
                if any(w in fold(left) for w in ROLE_WORDS):
                    role, names = left, right
                elif any(w in fold(right) for w in ROLE_WORDS):
                    role, names = right, left
            pieces = [p.strip(" .") for p in re.split(r",|\s+i\s+|\s+oraz\s+", names) if p.strip(" .")]
            for p in pieces:
                if _looks_like_person(p):
                    titles = TITLE_RE.match(p.strip())
                    people.append({
                        "name": TITLE_RE.sub("", p.strip()).strip(),
                        "titles": titles.group(0).strip() if titles else None,
                        "role": role,
                        "source_text": line,
                    })
    return people


def split_keywords(raw: str | None) -> list[str]:
    if not raw:
        return []
    parts = re.split(r"[,;•\n]|\s+[-–]\s+", raw)
    out = [clean_text(p).strip(" .") for p in parts]
    return list(dict.fromkeys(p for p in out if p))


def _join(values: list[str] | None) -> str | None:
    if not values:
        return None
    return "\n\n".join(v for v in values if v) or None


def _slug(url: str | None) -> str | None:
    if not url:
        return None
    return url.rstrip("/").rsplit("/", 1)[-1] or None


def _file_key(record_id: str) -> str:
    """Short, filesystem-safe name (Windows path limit) that stays unique."""
    safe = re.sub(r"[^a-z0-9-]+", "-", record_id.lower()).strip("-")[:60]
    return f"{safe}-{hashlib.sha1(record_id.encode()).hexdigest()[:10]}"


# --- record ------------------------------------------------------------------
def build_record(
    card: Parsed,
    detail: Parsed | None,
    *,
    list_fetched_at: str | None,
    detail_fetched_at: str | None,
    detail_error: str | None = None,
    today: date | None = None,
) -> dict:
    """Merge one list card with its detail page into a radar.record/v1 dict."""
    merged: dict[str, list[str]] = dict(detail.fields) if detail else {}
    merged.update(card.fields)  # list card is the authority for metadata (and the only one with region/keywords)
    get = lambda k: _join(merged.get(k))  # noqa: E731

    detail_url = card.detail_url
    title = get("title") or card.title or (detail.title if detail else None) or ""
    record_id = _slug(detail_url) or "untitled-" + hashlib.sha1(fold(title).encode()).hexdigest()[:12]

    total, cur1 = parse_money(get("total_value"))
    grant, cur2 = parse_money(get("grant_value"))
    period = parse_period(get("period"), today=today)
    voivodeships, nationwide = parse_voivodeships(get("region"))

    ben_orgs, ben_people = parse_parties(get("beneficiaries"), "beneficiary")
    par_orgs, par_people = parse_parties(get("partners"), "partner")
    team = parse_team(merged.get("team", []))

    narrative = {k: get(k) for k in NARRATIVE_KEYS}
    intro = detail.intro if detail else None
    other = (detail.other if detail else []) + card.other
    narrative["other"] = [o for o in other if o["text"]]

    llm_parts = [f"Tytuł: {title}"]
    intro_repeats_problem = bool(intro and narrative["problem"]
                                 and fold(narrative["problem"]).startswith(fold(intro)[:80]))
    if intro and not intro_repeats_problem:
        llm_parts.append(f"{NARRATIVE_HEADINGS['intro']}:\n{intro}")
    for k in NARRATIVE_KEYS:
        if narrative[k]:
            llm_parts.append(f"{NARRATIVE_HEADINGS[k]}:\n{narrative[k]}")
    if get("team"):
        llm_parts.append(f"Zespół:\n{get('team')}")
    text_for_llm = "\n\n".join(llm_parts)
    narrative_chars = sum(len(narrative[k] or "") for k in NARRATIVE_KEYS if k != "advice") + len(intro or "")

    blocking: list[str] = []
    warnings: list[str] = []
    if not detail_url:
        blocking.append("no_detail_page")
    elif detail_error:
        blocking.append(f"detail_fetch_failed: {detail_error}")
    elif detail is None:
        blocking.append("detail_not_fetched")
    if detail is not None or not detail_url:
        # the commercialisation template has no "problem" section but describes the product instead
        if not narrative["problem"] and not narrative["market_readiness"]:
            blocking.append("missing_problem")
        if narrative_chars < MIN_TEXT_CHARS:
            blocking.append("short_text")
        if not narrative["users"]:
            warnings.append("missing_users")
    if get("total_value") and total is None:
        warnings.append("total_value_unparsed")
    if get("grant_value") and grant is None:
        warnings.append("grant_value_unparsed")
    if not get("period"):
        warnings.append("period_missing")
    elif period.start is None:
        warnings.append("period_unparsed")
    if not get("region"):
        warnings.append("region_missing")
    elif not voivodeships and not nationwide:
        warnings.append("region_unparsed")
    if not ben_orgs:
        warnings.append("no_beneficiary_organisation")
    if not title:
        blocking.append("missing_title")

    content = {"card": card.to_json(), "detail": detail.to_json() if detail else None}
    content_hash = hashlib.sha256(json.dumps(content, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

    return {
        "schema": RECORD_SCHEMA,
        "source": SOURCE,
        "source_name": SOURCE_NAME,
        "record_id": record_id,
        "url": detail_url,
        "list_url": LIST_URL,
        "content_hash": content_hash,
        "record_type": "funded_project_success_story",
        "language": "pl",
        "title": title,
        "intro": intro,
        "text": narrative,
        "text_for_llm": text_for_llm,
        "organizations": ben_orgs + par_orgs,
        "people": ben_people + par_people + team,
        "funding": {
            "operator": "NCBR",
            "programme": get("programme"),
            "contest": get("contest"),
            "total_value": total,
            "grant_value": grant,
            "currency": cur1 or cur2,
            "grant_share": round(grant / total, 4) if total and grant else None,
            "raw": {"total_value": get("total_value"), "grant_value": get("grant_value")},
        },
        "period": period.as_dict(),
        "region": {"voivodeships": voivodeships, "nationwide": nationwide, "raw": get("region")},
        "keywords": split_keywords(get("keywords")),
        "extra": {k: get(k) for k in ("thesis_title",) if get(k)},
        "rights": {
            "licence": "unknown",
            "llm_may_read_fulltext": True,
            "note": "Publiczna strona gov.pl (NCBR); warunki ponownego wykorzystania do potwierdzenia.",
        },
        "quality": {
            "status": "needs_review" if blocking else "ok",
            "blocking": blocking,
            "warnings": warnings,
            "narrative_chars": narrative_chars,
        },
        "provenance": {
            "connector": f"radar.sources.ncbr/{CONNECTOR_VERSION}",
            "list_fetched_at": list_fetched_at,
            "detail_fetched_at": detail_fetched_at,
        },
    }


# --- raw store + harvest -----------------------------------------------------
class RawStore:
    """Raw pages on disk (the `raw` layer). A cached page is reused unless refresh=True,
    which also makes a full offline rebuild possible (demo mode)."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def _paths(self, name: str) -> tuple[Path, Path]:
        return self.root / f"{name}.html", self.root / f"{name}.meta.json"

    def get(self, name: str) -> tuple[str, dict] | None:
        html_path, meta_path = self._paths(name)
        if not html_path.exists():
            return None
        meta = json.loads(meta_path.read_text("utf-8")) if meta_path.exists() else {}
        return html_path.read_text("utf-8"), meta

    def put(self, name: str, resp: Response) -> dict:
        html_path, meta_path = self._paths(name)
        html_path.parent.mkdir(parents=True, exist_ok=True)
        meta = {"url": resp.url, "status": resp.status, "fetched_at": resp.fetched_at,
                "sha256": hashlib.sha256(resp.text.encode()).hexdigest()}
        html_path.write_text(resp.text, "utf-8")
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=1), "utf-8")
        return meta


@dataclass
class HarvestStats:
    cards: int = 0
    records: int = 0
    duplicates: int = 0
    fetched: int = 0
    cached: int = 0
    fetch_errors: int = 0
    status: Counter = field(default_factory=Counter)
    reasons: Counter = field(default_factory=Counter)

    def summary(self) -> str:
        lines = [
            f"cards on list page: {self.cards}",
            f"records: {self.records} (duplicates skipped: {self.duplicates})",
            f"detail pages: fetched {self.fetched}, from cache {self.cached}, errors {self.fetch_errors}",
            "quality: " + ", ".join(f"{k}={v}" for k, v in self.status.most_common()),
        ]
        if self.reasons:
            lines.append("reasons: " + ", ".join(f"{k}={v}" for k, v in self.reasons.most_common()))
        return "\n".join(lines)


def harvest(
    store: RawStore,
    *,
    fetcher: Callable[[str], Response] = fetch,
    limit: int | None = None,
    delay: float = 1.0,
    refresh: bool = False,
    offline: bool = False,
    today: date | None = None,
    stats: HarvestStats | None = None,
) -> Iterator[dict]:
    """Yield one normalized record per project card. Never drops a card: problems become
    quality reasons, so counts reconcile (cards = records + duplicates)."""
    stats = stats if stats is not None else HarvestStats()
    cached = None if refresh else store.get("list")
    if cached:
        list_html, list_meta = cached
    elif offline:
        raise FileNotFoundError(f"no cached list page in {store.root} (run once online)")
    else:
        resp = fetcher(LIST_URL)
        list_meta = store.put("list", resp)
        list_html = resp.text

    cards = parse_list(list_html)
    stats.cards = len(cards)
    seen: set[str] = set()
    first_request = True
    for card in cards:
        if limit is not None and stats.records >= limit:
            break
        key = card.detail_url or f"title:{fold(card.title or '')}"
        if key in seen:
            stats.duplicates += 1
            continue
        seen.add(key)

        detail, detail_meta, error = None, {}, None
        if card.detail_url:
            name = "detail/" + _file_key(_slug(card.detail_url) or card.detail_url)
            got = None if refresh else store.get(name)
            if got:
                stats.cached += 1
            elif not offline:
                if not first_request and delay:
                    time.sleep(delay)
                first_request = False
                try:
                    resp = fetcher(card.detail_url)
                    store.put(name, resp)
                    got = (resp.text, {"fetched_at": resp.fetched_at})
                    stats.fetched += 1
                except FetchError as e:
                    error = str(e)
                    stats.fetch_errors += 1
            if got:
                detail_meta = got[1]
                detail = parse_detail(got[0])
                if detail is None:
                    error = ("broken link: page is the gov.pl portal home, not a project"
                             if "<title>Portal Gov.pl</title>" in got[0] else "detail page has no <article>")

        record = build_record(
            card,
            detail,
            list_fetched_at=list_meta.get("fetched_at"),
            detail_fetched_at=detail_meta.get("fetched_at"),
            detail_error=error,
            today=today,
        )
        stats.records += 1
        stats.status[record["quality"]["status"]] += 1
        for r in record["quality"]["blocking"]:
            stats.reasons[r.split(":")[0]] += 1
        yield record


CSV_COLUMNS = ["record_id", "title", "beneficiaries", "contest", "total_value", "grant_value",
               "period_start", "period_end", "status", "voivodeships", "keywords", "quality", "reasons", "url"]


def _csv_row(r: dict) -> dict:
    return {
        "record_id": r["record_id"],
        "title": r["title"],
        "beneficiaries": "; ".join(o["name"] for o in r["organizations"] if o["role"] == "beneficiary"),
        "contest": r["funding"]["contest"],
        "total_value": r["funding"]["total_value"],
        "grant_value": r["funding"]["grant_value"],
        "period_start": r["period"]["start"],
        "period_end": r["period"]["end"],
        "status": r["period"]["status"],
        "voivodeships": ", ".join(r["region"]["voivodeships"]) or ("cała Polska" if r["region"]["nationwide"] else ""),
        "keywords": ", ".join(r["keywords"]),
        "quality": r["quality"]["status"],
        "reasons": "; ".join(r["quality"]["blocking"] + r["quality"]["warnings"]),
        "url": r["url"],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default="data/normalized/ncbr.jsonl", help="JSONL output (one record per line)")
    ap.add_argument("--csv", default=None, help="optional CSV view for people")
    ap.add_argument("--raw-dir", default="data/raw/ncbr", help="where raw pages are cached")
    ap.add_argument("--limit", type=int, default=None, help="stop after N records")
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between detail requests")
    ap.add_argument("--refresh", action="store_true", help="refetch pages even if cached")
    ap.add_argument("--offline", action="store_true", help="use cached raw pages only, no network")
    args = ap.parse_args(argv)

    store = RawStore(Path(args.raw_dir))
    stats = HarvestStats()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    rows = []
    started = datetime.now(timezone.utc)
    with tmp.open("w", encoding="utf-8") as fh:
        for rec in harvest(store, limit=args.limit, delay=args.delay, refresh=args.refresh,
                           offline=args.offline, stats=stats):
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            rows.append(_csv_row(rec))
            if stats.records % 25 == 0:
                print(f"... {stats.records} records", file=sys.stderr)
    tmp.replace(out)
    if args.csv:
        Path(args.csv).parent.mkdir(parents=True, exist_ok=True)
        with open(args.csv, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=CSV_COLUMNS, delimiter=";")
            w.writeheader()
            w.writerows(rows)
    secs = (datetime.now(timezone.utc) - started).total_seconds()
    print(stats.summary(), file=sys.stderr)
    print(f"wrote {stats.records} records to {out} in {secs:.0f}s", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
