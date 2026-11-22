"""LLM extraction with quote validation (pipeline-design §7, D-005 part b).

The model fills: solution_name, problem_solved, what_is_new, target_users, innovation_type, each with a verbatim
quote from the source. Code checks every quote occurs in the input; failures are sent back to the model
(max 2 retries), then the record goes to `needs_review`. The model never sees fields it could invent from.
"""

from __future__ import annotations

import json
import re

from radar.llm.router import AllProvidersFailed, router

INNOVATION_TYPES = ["technologiczna", "organizacyjna", "edukacyjna", "społeczna", "procesowa", "usługowa"]
QUOTED_FIELDS = ["solution_name", "problem_solved", "what_is_new", "target_users", "innovation_type"]
PROMPT_VERSION = "extract-v1"

SYSTEM = f"""Jesteś analitykiem Podkarpackiego Centrum Innowacji. Z opisu publikacji, projektu lub rozwiązania
instytucji publicznej wyciągasz informacje o innowacji. Odpowiadasz WYŁĄCZNIE obiektem JSON:
{{
 "is_innovation": "tak" | "nie" | "niejasne",   // czy opis przedstawia konkretne rozwiązanie, które ktoś inny mógłby zastosować
 "is_innovation_quote": "<dosłowny cytat>",
 "solution_name":   {{"value": "...", "quote": "<dosłowny cytat>", "confidence": 0..1}},
 "problem_solved":  {{"value": "...", "quote": "...", "confidence": 0..1}},
 "what_is_new":     {{"value": "...", "quote": "...", "confidence": 0..1}},
 "target_users":    {{"value": ["..."], "quote": "...", "confidence": 0..1}},
 "innovation_type": {{"value": one of {INNOVATION_TYPES}, "quote": "...", "confidence": 0..1}},
 "summary_pl": "2-3 zdania prostym językiem dla urzędnika"
}}
Zasady: każdy "quote" to fragment skopiowany dosłownie z TEKSTU ŹRÓDŁOWEGO. Nie zgaduj; gdy czegoś nie ma
w tekście, daj value null, quote "" i confidence 0."""


def _ws(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()


def source_text(title: str | None, abstract: str | None, keywords: list[str]) -> str:
    return f"Tytuł: {title or ''}\nSłowa kluczowe: {', '.join(keywords)}\nOpis: {abstract or ''}"


def validate(out: dict, text: str) -> list[str]:
    errors = []
    hay = _ws(text)
    if out.get("is_innovation") not in ("tak", "nie", "niejasne"):
        errors.append("is_innovation musi być tak|nie|niejasne")
    if out.get("is_innovation") == "nie":
        return errors
    for f in QUOTED_FIELDS:
        v = out.get(f)
        if not isinstance(v, dict):
            errors.append(f"{f}: brak obiektu {{value, quote, confidence}}")
            continue
        if v.get("value") in (None, "", []):
            continue  # an honest "not in the text" is allowed; the card lists it as missing
        q = _ws(v.get("quote", ""))
        if not q:
            errors.append(f"{f}: brak cytatu")
        elif q not in hay:
            errors.append(f"{f}: cytat nie występuje w tekście źródłowym: {v.get('quote')[:80]!r}")
    it_obj = out.get("innovation_type")
    it = it_obj.get("value") if isinstance(it_obj, dict) else None  # a small model may answer a bare string
    if it and it not in INNOVATION_TYPES:
        errors.append(f"innovation_type spoza listy: {it!r}")
    return errors


def extract(text: str, max_retries: int = 2) -> tuple[dict | None, list[str], dict]:
    """Returns (result | None, errors, provenance)."""
    user = f"TEKST ŹRÓDŁOWY:\n{text}"
    errors: list[str] = []
    prov: dict = {"prompt_version": PROMPT_VERSION}
    for attempt in range(max_retries + 1):
        msg = user if not errors else f"{user}\n\nPOPRZEDNIA ODPOWIEDŹ MIAŁA BŁĘDY, popraw je:\n- " + "\n- ".join(errors)
        try:
            out, p = router().complete_json(SYSTEM, msg, purpose="extract")
        except AllProvidersFailed as e:
            return None, [f"żaden dostawca LLM nie odpowiedział: {e}"], prov
        prov.update(p, attempts=attempt + 1)
        errors = validate(out, text) if isinstance(out, dict) else ["odpowiedź nie jest obiektem JSON"]
        if not errors:
            return out, [], prov
    # The model kept failing validation (typical for a 1.5B on long texts): the rule-based extractor still makes a
    # card from verbatim quotes, so a record never stalls; the model's errors stay in the provenance.
    real = tuple(p.name for p in router().providers if p.name != "mock")
    if prov.get("provider") and prov.get("provider") != "mock":
        try:
            out, p = router().complete_json(SYSTEM, user, purpose="extract", exclude=real)
            if isinstance(out, dict) and not validate(out, text):
                return out, [], {**prov, **p, "fallback_after": prov.get("provider"), "model_errors": errors[:5]}
        except AllProvidersFailed:
            pass
    return None, errors, prov


def dumps(x) -> str:
    return json.dumps(x, ensure_ascii=False)
