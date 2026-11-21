"""Extraction stage: from a normalized record to the fields an official needs, each with a quote.

The LLM (or the offline rules) only fills these fields. Code then checks every quote against the
source text; a field whose quote is not in the source is retried, then dropped and flagged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol

from .text import fold

PROMPT_VERSION = "extract/v1"

INNOVATION_TYPES = ["technologiczna", "produktowa", "procesowa", "organizacyjna", "edukacyjna", "społeczna", "usługowa"]
RECIPIENT_TYPES = [
    "gmina_miasto",          # JST szczebla gminnego
    "powiat_wojewodztwo",    # JST wyższego szczebla
    "szkola",
    "uczelnia",
    "instytut_badawczy",
    "ochrona_zdrowia",
    "administracja_sluzby",  # administracja rządowa, policja, straż, służby
    "przemysl",
    "msp",
    "energetyka_media",
    "transport",
    "rolnictwo",
    "ngo",
    "mieszkancy",
    "inne",
]
MATURITY_SIGNALS = [
    "badania_laboratoryjne",
    "prototyp",
    "demonstrator",
    "testy_w_warunkach_rzeczywistych",
    "pilotaz",
    "zgloszenie_patentowe",
    "patent",
    "wdrozenie_u_beneficjenta",
    "wdrozenie_poza_instytucja",
    "produkt_na_rynku",
    "licencja",
    "spin_off",
]
SECTORS = ["motoryzacja", "lotnictwo", "kosmos", "ICT", "jakosc_zycia", "zdrowie", "energia", "srodowisko",
           "edukacja", "administracja", "przemysl", "budownictwo", "rolnictwo_zywnosc", "transport", "inne"]
PCI_PRIORITY_SECTORS = {"motoryzacja", "lotnictwo", "kosmos", "ICT", "jakosc_zycia"}

QUOTED_FIELDS = ("solution_name", "problem_solved", "what_is_new", "requirements")
MIN_QUOTE_CHARS = 12


def _quoted(desc: str) -> dict:
    return {
        "type": "object",
        "properties": {
            "value": {"type": "string", "description": desc},
            "quote": {"type": "string", "description": "dosłowny fragment tekstu źródłowego potwierdzający wartość; pusty, gdy brak"},
        },
        "required": ["value", "quote"],
        "additionalProperties": False,
    }


EXTRACTION_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "is_innovation": {"type": "string", "enum": ["tak", "nie", "niejasne"]},
        "is_innovation_quote": {"type": "string"},
        "solution_name": _quoted("krótka nazwa rozwiązania (do 12 słów)"),
        "problem_solved": _quoted("jaki problem rozwiązuje, 1-2 zdania"),
        "what_is_new": _quoted("co jest nowego względem dotychczasowych rozwiązań, 1 zdanie"),
        "requirements": _quoted("co jest potrzebne do wdrożenia u innego odbiorcy (koszt, sprzęt, kompetencje); pusty, gdy tekst o tym nie mówi"),
        "innovation_type": {"type": "string", "enum": INNOVATION_TYPES},
        "innovation_type_quote": {"type": "string"},
        "target_users": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "who": {"type": "string"},
                    "recipient_type": {"type": "string", "enum": RECIPIENT_TYPES},
                    "quote": {"type": "string"},
                },
                "required": ["who", "recipient_type", "quote"],
                "additionalProperties": False,
            },
        },
        "maturity_signals": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "signal": {"type": "string", "enum": MATURITY_SIGNALS},
                    "quote": {"type": "string"},
                },
                "required": ["signal", "quote"],
                "additionalProperties": False,
            },
        },
        "sectors": {"type": "array", "items": {"type": "string", "enum": SECTORS}},
        "summary_pl": {"type": "string", "description": "2-3 zdania prostym językiem dla urzędnika"},
    },
    "required": ["is_innovation", "is_innovation_quote", "solution_name", "problem_solved", "what_is_new",
                 "requirements", "innovation_type", "innovation_type_quote", "target_users",
                 "maturity_signals", "sectors", "summary_pl"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """Jesteś analitykiem Radaru Innowacji. Czytasz opis projektu z publicznej bazy i wypełniasz \
pola karty innowacji dla urzędnika, który zdecyduje, komu ją przekazać.

Zasady:
- Korzystaj wyłącznie z tekstu źródłowego. Niczego nie dopowiadaj z wiedzy ogólnej.
- Każde pole z cytatem: "quote" to dosłownie skopiowany fragment tekstu źródłowego (bez zmian w słowach, \
od kilku słów do jednego-dwóch zdań), który potwierdza wartość. Kod sprawdza, czy cytat występuje w tekście; \
cytat sparafrazowany zostanie odrzucony.
- Gdy tekst czegoś nie mówi, zostaw "value" i "quote" puste (dla list: pusta lista). Brak danych jest \
lepszy niż zgadywanie.
- target_users: konkretne grupy odbiorców wymienione w tekście, każda z typem z listy i cytatem.
- maturity_signals: tylko sygnały opisane wprost (np. zbudowano demonstrator, przeprowadzono pilotaż, \
złożono zgłoszenie patentowe, wdrożono u klienta), każdy z cytatem.
- is_innovation: "tak", gdy opis przedstawia konkretne rozwiązanie, które ktoś inny mógłby zastosować; \
"nie", gdy to wyłącznie badanie podstawowe lub ogólna działalność; inaczej "niejasne".
- summary_pl: 2-3 zdania, prosty język, bez żargonu."""


class LLMError(Exception):
    pass


class Extractor(Protocol):
    """A provider: returns a dict matching EXTRACTION_SCHEMA. `feedback` lists errors from the previous try."""

    name: str
    model: str | None

    def extract(self, source_text: str, record: dict, feedback: list[str] | None = None) -> dict: ...


# --- source text and quote checks -------------------------------------------
def source_text(record: dict) -> str:
    """Everything the extractor may quote: narrative plus metadata lines."""
    parts = [record.get("text_for_llm") or record.get("title") or ""]
    f = record.get("funding") or {}
    meta = [("Program", f.get("programme")), ("Konkurs", f.get("contest")),
            ("Słowa kluczowe", ", ".join(record.get("keywords") or []) or None)]
    parts += [f"{k}: {v}" for k, v in meta if v]
    return "\n\n".join(p for p in parts if p)


def _norm(text: str) -> str:
    text = fold(text)
    text = re.sub(r"[„”\"'`«»]", "", text)
    text = re.sub(r"[–—‐-]", "-", text)
    return re.sub(r"\s+", " ", text).strip(" .,;:")


def quote_in_source(quote: str, src_norm: str) -> bool:
    q = _norm(quote)
    if len(q) >= MIN_QUOTE_CHARS:
        return q in src_norm
    # short names ("Cypherdog") only as whole words, so "sie" or "dla" never count as evidence
    return len(q) >= 3 and re.search(rf"(?<![a-z0-9]){re.escape(q)}(?![a-z0-9])", src_norm) is not None


def validate(data: dict, src: str) -> list[str]:
    """Schema-level and quote checks. Returns human-readable errors (empty = valid)."""
    errors: list[str] = []
    src_norm = _norm(src)
    for key in EXTRACTION_SCHEMA["required"]:
        if key not in data:
            errors.append(f"brak pola {key}")
    if errors:
        return errors
    if data["is_innovation"] not in ("tak", "nie", "niejasne"):
        errors.append("is_innovation spoza listy")
    if data["innovation_type"] not in INNOVATION_TYPES:
        errors.append(f"innovation_type spoza listy: {data['innovation_type']}")
    for key in QUOTED_FIELDS:
        item = data.get(key) or {}
        if item.get("value") and not quote_in_source(item.get("quote", ""), src_norm):
            errors.append(f"{key}: cytat nie występuje w tekście źródłowym")
    for i, u in enumerate(data.get("target_users") or []):
        if u.get("recipient_type") not in RECIPIENT_TYPES:
            errors.append(f"target_users[{i}]: typ spoza listy")
        if not quote_in_source(u.get("quote", ""), src_norm):
            errors.append(f"target_users[{i}] ({u.get('who')}): cytat nie występuje w tekście źródłowym")
    for i, s in enumerate(data.get("maturity_signals") or []):
        if s.get("signal") not in MATURITY_SIGNALS:
            errors.append(f"maturity_signals[{i}]: sygnał spoza listy")
        if not quote_in_source(s.get("quote", ""), src_norm):
            errors.append(f"maturity_signals[{i}] ({s.get('signal')}): cytat nie występuje w tekście źródłowym")
    for s in data.get("sectors") or []:
        if s not in SECTORS:
            errors.append(f"sektor spoza listy: {s}")
    return errors


def drop_invalid(data: dict, src: str) -> tuple[dict, list[str]]:
    """Last resort after retries: remove every unverifiable claim and say which ones."""
    src_norm = _norm(src)
    dropped: list[str] = []
    clean = dict(data)
    for key in QUOTED_FIELDS:
        item = dict(clean.get(key) or {"value": "", "quote": ""})
        if item.get("value") and not quote_in_source(item.get("quote", ""), src_norm):
            dropped.append(key)
            item = {"value": "", "quote": ""}
        clean[key] = item
    users = [u for u in clean.get("target_users") or []
             if u.get("recipient_type") in RECIPIENT_TYPES and quote_in_source(u.get("quote", ""), src_norm)]
    if len(users) < len(clean.get("target_users") or []):
        dropped.append("target_users (część)")
    clean["target_users"] = users
    signals = [s for s in clean.get("maturity_signals") or []
               if s.get("signal") in MATURITY_SIGNALS and quote_in_source(s.get("quote", ""), src_norm)]
    if len(signals) < len(clean.get("maturity_signals") or []):
        dropped.append("maturity_signals (część)")
    clean["maturity_signals"] = signals
    clean["sectors"] = [s for s in clean.get("sectors") or [] if s in SECTORS]
    if clean.get("innovation_type") not in INNOVATION_TYPES:
        clean["innovation_type"] = "technologiczna"
        dropped.append("innovation_type")
    return clean, dropped


@dataclass
class ExtractionResult:
    data: dict
    provider: str
    model: str | None
    attempts: int
    dropped: list[str] = field(default_factory=list)
    errors_seen: list[str] = field(default_factory=list)
    fallback_reason: str | None = None


def run_extraction(record: dict, providers: list[Extractor], max_retries: int = 2) -> ExtractionResult:
    """Try providers in order (e.g. Claude, then offline rules). Each provider gets up to
    `max_retries` retries with the validation errors as feedback."""
    src = source_text(record)
    fallback_reason = None
    last_exc: Exception | None = None
    for provider in providers:
        feedback: list[str] | None = None
        seen: list[str] = []
        data: dict | None = None
        try:
            for attempt in range(1, max_retries + 2):
                data = provider.extract(src, record, feedback)
                errors = validate(data, src)
                if not errors:
                    return ExtractionResult(data, provider.name, provider.model, attempt,
                                            errors_seen=seen, fallback_reason=fallback_reason)
                seen += errors
                feedback = errors
            assert data is not None
            if all(k in data for k in EXTRACTION_SCHEMA["required"]):
                clean, dropped = drop_invalid(data, src)
                return ExtractionResult(clean, provider.name, provider.model, max_retries + 1, dropped, seen,
                                        fallback_reason)
            fallback_reason = f"{provider.name}: niepełna odpowiedź po {max_retries + 1} próbach"
        except LLMError as e:
            last_exc = e
            fallback_reason = f"{provider.name}: {e}"
    raise LLMError(f"żaden dostawca nie dał wyniku ({fallback_reason})") from last_exc
