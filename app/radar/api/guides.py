"""Guides: five fictional characters (Higgsfield portraits) who tell a project's story out loud and help choose.

The narration is built from facts the pipeline already has (card, business case, investor signals) by rules, so
it always works. When a small local model is configured (Bielik 1.5B behind llama.cpp, RADAR_LOCAL_LLM_URL), it may
rewrite those facts into spoken Polish; the result is accepted only if it adds no number that is not in the facts
and is a finished text of sane length; otherwise the rule text is used. Each (card, guide) is generated once and
kept in the card's `brief`, so the model never runs twice for the same story. The model runs only offline, on the
operator's request (never while a user waits). Voices are pre-recorded mp3 files (ElevenLabs, one voice per guide,
`static/audio/`); no speech is synthesized in the browser or on request.
"""

from __future__ import annotations

import os
import re
import threading
import time

import httpx
from fastapi import APIRouter, Header, HTTPException
from sqlalchemy.orm.attributes import flag_modified

from radar.api.auth import operator
from radar.basal.classifier import label_pl
from radar.config import get_settings
from radar.db import session
from radar.models import Card

router = APIRouter(prefix="/api")

GUIDES = {
    "radek": {"name": "Radek", "role": "przewodnik po radarze", "for": ["innowatorzy", ""], "pitch": 1.15, "rate": 1.05},
    "ada": {"name": "Ada", "role": "przewodniczka inwestorów", "for": ["inwestorzy"], "pitch": 1.1, "rate": 1.0},
    "tomek": {"name": "Tomek", "role": "przewodnik wdrożeń dla samorządów i wykonawców", "for": ["samorzady", "startupy"], "pitch": 0.9, "rate": 1.0},
    "ola": {"name": "Ola", "role": "przewodniczka szkół", "for": ["szkoly"], "pitch": 1.05, "rate": 0.98},
    "profesor": {"name": "Profesor Marek", "role": "przewodnik uczelni i nauki", "for": ["uczelnie"], "pitch": 0.85, "rate": 0.95},
}
LVL = {"exploring": "na etapie badań", "tech_ready": "z gotową technologią", "business_ready": "gotowy do wdrożenia", "market_ready": "już na rynku"}
TIDY = re.compile(r"^\s*Tytuł:.*?(?=Zajawka:|Jaki problem|Opis:|$)|\b(Zajawka|Jaki problem rozwiązuje projekt|Opis projektu|Opis):\s*", re.I | re.S)
NUM = re.compile(r"\d+(?:[ .,]\d+)*")


def plural(n: int, one: str, few: str, many: str) -> str:
    """Polish plural: 1 milion, 2-4 miliony, 5-21 milionów, 22-24 miliony…"""
    if n == 1:
        return one
    return few if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14) else many


def zl(n) -> str:
    if not n:
        return "nieznana kwota"
    if n >= 1e6:
        m = round(n / 1e6, 1)
        if m != int(m):  # fractions take the genitive singular: 1,6 miliona
            return f"{str(m).replace('.', ',')} miliona złotych"
        return f"{int(m)} {plural(int(m), 'milion', 'miliony', 'milionów')} złotych"
    k = round(n / 1000)
    return f"{k} {plural(k, 'tysiąc', 'tysiące', 'tysięcy')} złotych"


def sentence(text: str | None, limit: int = 220) -> str:
    t = " ".join(TIDY.sub("", text or "").split())
    m = re.match(r"(.{40,%d}?[.!?])(\s|$)" % limit, t)
    return (m.group(1) if m else t[:limit].rsplit(" ", 1)[0] + "…") if t else ""


def facts(card: Card, guide: str) -> list[str]:
    """Rule narration: 4-6 short spoken sentences, emphasis by guide."""
    from radar.business import business_case
    from radar.investor import signals

    r = card.record
    bc = business_case(r, card) if card.maturity else None
    title = card.solution_name or r.title or "ten projekt"
    org = (r.affiliations or [None])[0]
    where = f" (województwo {r.voivodeship})" if r.voivodeship else ""
    g = GUIDES[guide]
    out = [f"Cześć, tu {g['name']}, {g['role']}.",
           f"Opowiem o projekcie „{title[:120]}”" + (f", który prowadzi {org[:90]}{where}." if org else f"{where}."),
           sentence(card.problem_solved or card.summary_pl, 170)]
    path = ((card.assessment or {}).get("paths") or [{}])[0]
    step = ((path.get("steps") or [{}])[0]).get("step")
    if bc:
        if guide == "ada":
            from sqlalchemy.orm import object_session

            sig = signals(object_session(card), r, card, bc)
            out.append(f"To pomysł {LVL.get(card.maturity, '')}, gotowość inwestycyjna {sig['readiness']['score']} na 100.")
            if bc["valuation"].get("open_model"):
                out.append(f"To model działania przekazywany otwarcie, bez licencji; odbiorcy oszczędzą razem około {zl(bc['valuation']['public_value_3y_pln'])} w trzy lata.")
            else:
                out.append(f"Wartość licencji lub spółki szacujemy na {zl(sig['adjusted']['licence_or_spinoff_pln'])}, przy szansie wdrożenia {round(sig['adjusted']['success_probability'] * 100)} procent.")
        elif guide in ("tomek", "ola"):
            out.append(f"Wdrożenie u siebie kosztuje około {zl(bc['deploy_cost_pln'])}, a zwrot to {bc['payback'].replace('<', 'mniej niż')}.")
            if bc["funding"]:
                out.append(f"Można to sfinansować na przykład z programu {bc['funding'][0]['programme'].split(' — ')[0]}.")
        elif guide == "profesor":
            out.append(f"Projekt jest {LVL.get(card.maturity, '')}. Potencjalnych odbiorców jest {bc['adopters']['count']}, to {bc['adopters']['who'].split(' (')[0]}.")
            if bc["funding"]:
                out.append(f"Następny krok można sfinansować z programu {bc['funding'][0]['programme'].split(' — ')[0]}.")
        else:
            out.append(f"Projekt jest {LVL.get(card.maturity, '')}, a wdrożenie kosztuje około {zl(bc['deploy_cost_pln'])}.")
            out.append(f"Może z niego skorzystać {bc['adopters']['count']} odbiorców, czyli {bc['adopters']['who'].split(' (')[0]}.")
    if step:
        out.append(f"Pierwszy krok: {step}.")
    return [s for s in out if s]


SYSTEM = ("Jesteś przewodnikiem po innowacjach z polskich szkół, uczelni i samorządów. Streszczasz fakty w 2-3 krótkich "
          "zdaniach mówionych, po polsku, prostym językiem, jak do znajomego. Nie kopiujesz zdań z faktów. Nie dodajesz "
          "nowych faktów, liczb ani nazw. Odpowiadasz wyłącznie JSON.")
AUDIENCE = {"radek": "dla osoby, która pierwszy raz trafiła na radar", "ada": "dla inwestora", "tomek": "dla wójta lub dyrektora instytucji",
            "ola": "dla dyrektora szkoły", "profesor": "dla naukowca z uczelni"}
GBNF = r'''root ::= "{\"tekst\": \"" [^"\\\n]{100,420} "\"}"'''
# Public endpoint in front of one llama.cpp server shared with the pipeline: at most this many narrations run at once
# per API process; a request that finds the slot busy gets the rule text at once instead of queueing on the model.
MODEL_SLOTS = threading.BoundedSemaphore(int(os.environ.get("RADAR_GUIDE_LLM_CONCURRENCY", "1")))


def bielik(text: str, guide: str) -> tuple[str | None, float]:
    """Rewrite with the local small model. Returns (text or None, seconds)."""
    s = get_settings()
    url = os.environ.get("RADAR_GUIDE_LLM_URL") or s.local_llm_url  # guides may use the small model while the pipeline stays on rules
    if not url:
        return None, 0.0
    t0 = time.perf_counter()
    try:
        r = httpx.post(url.rstrip("/") + "/chat/completions", timeout=min(s.local_llm_timeout_s, 120), json={
            "model": s.local_llm_model, "temperature": 0.5, "max_tokens": 360, "grammar": GBNF,
            "messages": [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": "Fakty:\n" + "\n".join("- " + f for f in text.split("\n") if f.strip())
                          + f"\n\nNapisz streszczenie {AUDIENCE[guide]}. Zacznij od: Cześć, tu {GUIDES[guide]['name']}. "
                          + "Zwróć JSON {\"tekst\": \"...\"}."}]})
        r.raise_for_status()
        import json

        out = json.loads(r.json()["choices"][0]["message"]["content"]).get("tekst", "")
    except Exception:  # noqa: BLE001 - any model failure falls back to the rule text
        return None, time.perf_counter() - t0
    return validate(out, text), time.perf_counter() - t0


def validate(out: str, source: str) -> str | None:
    t = " ".join((out or "").split()).strip('"„” ')
    if t and t[-1] not in ".!?…":  # hit the length cap mid-sentence: keep the finished sentences
        cut = max(t.rfind(". "), t.rfind("! "), t.rfind("? "))
        t = t[:cut + 1] if cut > 0 else t
    if not 80 <= len(t) <= 700 or t[-1] not in ".!?…":
        return None
    norm = lambda x: re.sub(r"[ .,]", "", x)  # noqa: E731
    known = {norm(n) for n in NUM.findall(source)}
    if any(norm(n) not in known for n in NUM.findall(t)):  # an invented number: reject the whole text
        return None
    return t


@router.get("/guides")
def guides():
    return [{"key": k, "img": f"/static/guides/{k}.webp", **v} for k, v in GUIDES.items()]


def _guide_llm_url() -> str:
    return os.environ.get("RADAR_GUIDE_LLM_URL") or get_settings().local_llm_url


@router.get("/cards/{card_id}/pitch")
def pitch(card_id: int, guide: str = "radek", llm: bool = False, fresh: bool = False,
          x_operator_token: str | None = Header(default=None)):
    """Nothing is generated while a user waits: the UI gets the stored narration (prepared in advance by the
    operator with Bielik, `scripts/bielik_examples.py`) or the rule text built from the card's facts. Running the
    model (llm=1) or regenerating (fresh=1) is an operator action."""
    if guide not in GUIDES:
        raise HTTPException(404, "nieznany przewodnik")
    if fresh or llm:
        operator(x_operator_token)
    key = f"pitch_{guide}"
    # short read, then the model with no session open (it may take up to two minutes), then a short write
    with session() as s:
        c = s.get(Card, card_id)
        if c is None:
            raise HTTPException(404)
        cached = (c.brief or {}).get(key)
        # a rule text is final once the model has been tried for it (failed validation): no retry per request
        if cached and not fresh and (cached.get("by") != "reguły" or cached.get("model_tried") or not llm
                                     or not _guide_llm_url()):
            return {"card_id": card_id, "guide": guide, **cached, "cached": True}
        fl = facts(c, guide)
        sector = label_pl("sector", c.record.sector) if c.record.sector else None
    rules = " ".join(fl)
    text, secs, by, tried = rules, 0.0, "reguły", False
    if llm and _guide_llm_url() and MODEL_SLOTS.acquire(blocking=False):
        try:
            model_facts = [re.sub(r"^Opowiem o projekcie „.*?”,? ?(który prowadzi )?", "Projekt prowadzi ", f) if f.startswith("Opowiem") else f for f in fl[1:]]
            out, secs = bielik("\n".join(model_facts), guide)
            tried = True
        finally:
            MODEL_SLOTS.release()
        if out:
            hello = f"Cześć, tu {GUIDES[guide]['name']}."
            text, by = (out if out.startswith("Cześć") else f"{hello} {out}"), "bielik-1.5b"
    entry = {"text": text, "by": by, "rules": rules, "seconds": round(secs, 1), **({"model_tried": True} if tried else {})}
    with session() as s:
        c = s.get(Card, card_id)
        if c is not None:
            c.brief = {**(c.brief or {}), key: entry}
            flag_modified(c, "brief")
    return {"card_id": card_id, "guide": guide, **entry, "cached": False, "sector": sector}
