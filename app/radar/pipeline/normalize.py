"""Deterministic normalization (no LLM): source payload -> Record fields, driven by `mapping` in sources.yaml.

mapping value forms:
  title: "title[0]"                                 # JMESPath
  amount_eu: {expr: "euBudgets[0]", transform: pl_decimal}
  year: {expr: "date", transform: [first, year]}    # transforms are applied in order
  kind: {const: "project"}
"""

from __future__ import annotations

import html
import re
from typing import Any

from radar.sources.base import SourceSpec, search

FIELDS = {"title", "abstract", "language", "year", "doi", "url", "authors", "affiliations", "keywords",
          "licence", "region", "kind"}
LIST_FIELDS = {"authors", "affiliations", "keywords"}
TAG = re.compile(r"<[^>]+>")
YEAR = re.compile(r"(19|20)\d{2}")


def t_first(v):
    if isinstance(v, list):
        return next((x for x in v if x not in (None, "")), None)
    return v


def t_pl_decimal(v):
    """Kohesio: "336000000,00" -> 336000000.0 (also handles "1 234,5" and plain numbers)."""
    v = t_first(v)
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).replace(" ", "").replace(" ", "")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def t_year(v):
    v = t_first(v)
    if v is None:
        return None
    if isinstance(v, int):
        return v
    m = YEAR.search(str(v))
    return int(m.group(0)) if m else None


def t_doi(v):
    if isinstance(v, list):
        for x in v:
            d = t_doi(x)
            if d:
                return d
        return None
    if not v:
        return None
    s = str(v).strip().lower()
    for p in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "doi:"):
        s = s.removeprefix(p)
    return s if s.startswith("10.") else None


def t_strip_html(v):
    if isinstance(v, list):
        return [t_strip_html(x) for x in v]
    if v is None:
        return None
    return re.sub(r"\s+", " ", html.unescape(TAG.sub(" ", str(v)))).strip()


def t_join(v):
    return " ".join(str(x) for x in v if x) if isinstance(v, list) else v


def t_list(v):
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def t_split_semicolon(v):
    return [x.strip() for x in t_first(v).split(";") if x.strip()] if t_first(v) else []


TRANSFORMS = {
    "first": t_first, "pl_decimal": t_pl_decimal, "year": t_year, "doi": t_doi, "strip_html": t_strip_html,
    "join": t_join, "list": t_list, "split_semicolon": t_split_semicolon,
    "lower": lambda v: v.lower() if isinstance(v, str) else v,
}


def apply_mapping(spec: SourceSpec, payload: dict) -> tuple[dict, dict]:
    """Returns (record_fields, extra). Unknown target fields go to `extra` (e.g. amounts, dates, geo)."""
    fields: dict[str, Any] = {"kind": spec.kind}
    extra: dict[str, Any] = {}
    for target, rule in spec.mapping.items():
        if isinstance(rule, dict) and "const" in rule:
            value = rule["const"]
        else:
            expr = rule["expr"] if isinstance(rule, dict) else rule
            value = search(expr, payload)
            transforms = rule.get("transform", []) if isinstance(rule, dict) else []
            for name in [transforms] if isinstance(transforms, str) else transforms:
                value = TRANSFORMS[name](value)
        (fields if target in FIELDS else extra)[target] = value

    for f in LIST_FIELDS:
        fields[f] = [x for x in t_list(fields.get(f)) if x]
    for f in ("title", "abstract"):
        v = fields.get(f)
        if isinstance(v, list):
            v = t_first(v)
        fields[f] = t_strip_html(v) if v else None
    if fields.get("year") is not None and not isinstance(fields["year"], int):
        fields["year"] = t_year(fields["year"])
    if fields.get("doi"):
        fields["doi"] = t_doi(fields["doi"])
    for f in ("language", "url", "licence", "region"):
        if isinstance(fields.get(f), list):
            fields[f] = t_first(fields[f])
    return fields, extra


def quality_gate(fields: dict, min_chars: int) -> list[str]:
    reasons = []
    if not fields.get("title"):
        reasons.append("brak tytułu")
    if not fields.get("abstract"):
        reasons.append("brak opisu")
    elif len(fields["abstract"]) < min_chars:
        reasons.append(f"opis krótszy niż {min_chars} znaków")
    return reasons


def norm_title(t: str | None) -> str:
    """For near-duplicate detection: lowercase, no diacritics, no punctuation."""
    import unicodedata

    if not t:
        return ""
    t = unicodedata.normalize("NFKD", t.replace("ł", "l").replace("Ł", "L"))
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


_ROMAN = r"(?:i{1,3}|iv|vi{0,3}|ix|x)"
_PHASE = re.compile(rf"\b(?:etap|czesc|faza|edycja|transza|odcinek|cz)\s*(?:{_ROMAN}|\d+)\b"
                    rf"|\b(?:{_ROMAN}|\d+)\s*(?:etap|edycja|czesc)\b")
_PLACE = re.compile(r"\b(?:w|we|na terenie|dla|z terenu)\s+(?:gmin\w*|powiat\w*|miast\w*|miescie|wsi|wojewodztw\w*|obszar\w*)\b.*$"
                    r"|\b(?:gminy|gmin|powiatu|miasta)\s+\w+.*$")
_TRAILING_NO = re.compile(rf"(?:\s+{_ROMAN}|\s+\d+)+$")


def programme_key(t: str | None) -> str:
    """Title of the programme behind a project, for grouping (Kohesio): without the parenthesised scope, phase
    markers ("etap II", "część 2", "(I)") and a trailing place ("w Gminie Knurów", "na terenie gmin ..."), so
    "Czyste powietrze w Gminie Żytno" and "Czyste powietrze w gminie Młodzieszyn" share "czyste powietrze"."""
    k = norm_title(re.sub(r"\([^)]*\)", " ", t or ""))
    k = _PLACE.sub(" ", _PHASE.sub(" ", k))
    return _TRAILING_NO.sub("", re.sub(r"\s+", " ", k).strip()).strip()


def same_programme(a: str, b: str) -> bool:
    """Equal programme keys of 2+ words, or near-equal long ones (spelling, an extra word); short generic keys
    ("budowa budynku urzedu") must match exactly."""
    if not a or not b or len(a.split()) < 2:
        return False
    if a == b:
        return True
    from difflib import SequenceMatcher

    return min(len(a), len(b)) >= 25 and SequenceMatcher(None, a, b).ratio() >= 0.9
