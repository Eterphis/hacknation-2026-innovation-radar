"""Deterministic stages after extraction: maturity, scoring, path and recipients.

No LLM here. Every number has a rule and every rule produces a sentence for the official,
so the same input always gives the same card and the criteria are open to inspection.
"""

from __future__ import annotations

import re

from .extract import PCI_PRIORITY_SECTORS
from .text import fold

ASSESS_VERSION = "assess/v1"

# --- maturity -----------------------------------------------------------------
LEVELS = ["exploring", "tech_ready", "business_ready", "market_ready"]
LEVEL_PL = {
    "exploring": "badania (koncepcja, wyniki badań)",
    "tech_ready": "gotowa technologia (prototyp, demonstrator, pilotaż lub patent)",
    "business_ready": "gotowa do wdrożenia (wdrożona u twórcy, licencja lub spółka)",
    "market_ready": "na rynku (stosowana poza instytucją, która ją stworzyła)",
}
SIGNAL_LEVEL = {
    "badania_laboratoryjne": "exploring",
    "prototyp": "tech_ready",
    "demonstrator": "tech_ready",
    "testy_w_warunkach_rzeczywistych": "tech_ready",
    "pilotaz": "tech_ready",
    "zgloszenie_patentowe": "tech_ready",
    "patent": "tech_ready",
    "wdrozenie_u_beneficjenta": "business_ready",
    "licencja": "business_ready",
    "spin_off": "business_ready",
    "wdrozenie_poza_instytucja": "market_ready",
    "produkt_na_rynku": "market_ready",
}
SIGNAL_PL = {
    "badania_laboratoryjne": "badania laboratoryjne",
    "prototyp": "prototyp",
    "demonstrator": "demonstrator",
    "testy_w_warunkach_rzeczywistych": "testy w warunkach rzeczywistych",
    "pilotaz": "pilotaż",
    "zgloszenie_patentowe": "zgłoszenie patentowe",
    "patent": "patent",
    "wdrozenie_u_beneficjenta": "wdrożenie u twórcy",
    "licencja": "licencja",
    "spin_off": "spółka spin-off",
    "wdrozenie_poza_instytucja": "wdrożenie w innej instytucji",
    "produkt_na_rynku": "produkt na rynku",
}
NEXT_STEP = {
    "exploring": "prototyp lub pilotaż potwierdzający działanie poza laboratorium",
    "tech_ready": "pierwsze wdrożenie (u twórcy albo u odbiorcy) lub umowa licencyjna",
    "business_ready": "wdrożenie w co najmniej jednej innej instytucji",
    "market_ready": "skalowanie: kolejni odbiorcy, inne regiony",
}


def maturity(extraction: dict) -> dict:
    signals = extraction.get("maturity_signals") or []
    level = "exploring"
    evidence = []
    for s in signals:
        lvl = SIGNAL_LEVEL.get(s["signal"], "exploring")
        evidence.append({"signal": s["signal"], "label": SIGNAL_PL.get(s["signal"], s["signal"]),
                         "level": lvl, "quote": s["quote"]})
        if LEVELS.index(lvl) > LEVELS.index(level):
            level = lvl
    hidden = LEVELS.index(level) >= 1 and not any(e["level"] == "market_ready" for e in evidence)
    return {
        "level": level,
        "level_index": LEVELS.index(level) + 1,
        "level_pl": LEVEL_PL[level],
        "evidence": evidence,
        "missing": NEXT_STEP[level],
        "hidden": hidden,
        "hidden_pl": ("gotowe rozwiązanie bez śladu wdrożenia poza instytucją twórcy: ukryta innowacja"
                      if hidden else None),
    }


# --- scoring --------------------------------------------------------------------
CRITERIA = [
    ("dojrzalosc", "Dojrzałość"),
    ("przenaszalnosc", "Przenaszalność"),
    ("skala_problemu", "Skala problemu"),
    ("koszt_wdrozenia", "Koszt i wymagania wdrożenia"),
    ("dowody", "Siła dowodów"),
]
WEIGHTS = {k: 1.0 for k, _ in CRITERIA}
THRESHOLDS = [(3.8, "green", "rekomendowana do aktywnego kierowania do odbiorców"),
              (2.8, "yellow", "warto zweryfikować z ekspertem przed kierowaniem dalej"),
              (0.0, "red", "niski priorytet na dziś")]
LIGHT_PL = {"green": "zielone", "yellow": "żółte", "red": "czerwone"}
SCALE_RE = r"coraz wiecej|rosn|powszechn|wiele|w calej polsce|na swiecie|globaln|miliony|milion|tysiac|\d+\s?%|wszystkich"
COST_HINT_RE = (r"\btani[a-z]{0,3}\b|\bnisk[a-z]* koszt|\bobniz[a-z]* koszt|\bograniczen[a-z]* koszt|\bredukcj[a-z]* koszt"
                r"|\bbez dodatkowych|\bprost[a-z]* w (?:implementacji|wdrozeniu|obsludze|montazu)")
COST_BURDEN_RE = (r"\bkosztown|\bdrog(?:i|ie|a|iego)\b|\bduz[a-z]* nakład|\bspecjalistyczn[a-z]* (?:sprzet|aparatur)"
                  r"|\bwymaga[a-z]* (?:budowy|inwestycji)")


def _dots(score: int | None) -> str:
    return "brak danych" if score is None else "●" * score + "○" * (5 - score)


def score(record: dict, extraction: dict, mat: dict) -> dict:
    users = extraction.get("target_users") or []
    user_types = sorted({u["recipient_type"] for u in users})
    sectors = extraction.get("sectors") or []
    problem = (extraction.get("problem_solved") or {}).get("value") or ""
    requirement = (extraction.get("requirements") or {}).get("value") or ""
    narrative = fold(" ".join(v for k, v in (record.get("text") or {}).items() if isinstance(v, str)))
    out: dict[str, dict] = {}

    # Dojrzałość: straight from the maturity level.
    lvl = mat["level_index"]
    s = {1: 2, 2: 3, 3: 4, 4: 5}[lvl]
    if extraction.get("is_innovation") == "nie":
        s = 1
    out["dojrzalosc"] = {"score": s, "why": f"Poziom: {mat['level_pl']}."
                         + (f" Dowody: {', '.join(e['label'] for e in mat['evidence'])}." if mat["evidence"] else " Brak opisanych dowodów wdrożenia.")}

    # Przenaszalność: how many kinds of recipients the source itself names.
    n = len(user_types)
    s = 5 if n >= 4 else 4 if n == 3 else 3 if n == 2 else 2 if n == 1 else 1
    public = [t for t in user_types if t in ("gmina_miasto", "powiat_wojewodztwo", "szkola", "uczelnia",
                                               "ochrona_zdrowia", "administracja_sluzby", "instytut_badawczy")]
    out["przenaszalnosc"] = {"score": s, "why": (f"Źródło wymienia {n} rodzaj(e/ów) odbiorców" if n else "Źródło nie wymienia odbiorców")
                             + (f", w tym sektor publiczny ({len(public)})." if public else ".")}

    # Skala problemu: number of sectors plus wording about how widespread the problem is.
    widespread = bool(re.search(SCALE_RE, fold(problem + " " + narrative[:3000])))
    s = min(5, 1 + min(len(sectors), 3) + (1 if widespread else 0))
    out["skala_problemu"] = {"score": s, "why": f"Dziedziny zastosowań: {len(sectors)}"
                             + ("; opis wskazuje na powszechny lub rosnący problem." if widespread else "; brak informacji o skali problemu.")}

    # Koszt wdrożenia: scored only when the text says something; otherwise an explicit gap.
    if requirement or re.search(COST_HINT_RE, narrative) or re.search(COST_BURDEN_RE, narrative):
        cheap = bool(re.search(COST_HINT_RE, narrative))
        burden = bool(re.search(COST_BURDEN_RE, narrative))
        s = 4 if cheap and not burden else 2 if burden and not cheap else 3
        why = ("Tekst wskazuje na prostotę wdrożenia lub obniżenie kosztów u odbiorcy." if s == 4 else
               "Tekst wskazuje na wysokie nakłady lub specjalistyczny sprzęt." if s == 2 else
               "Tekst opisuje wymagania wdrożenia, bez jednoznacznej oceny kosztu.")
        out["koszt_wdrozenia"] = {"score": s, "why": why}
    else:
        out["koszt_wdrozenia"] = {"score": None, "why": "Brak danych o kosztach i wymaganiach wdrożenia."}

    # Dowody: how much of the card is backed by verified quotes.
    quoted = sum(1 for k in ("problem_solved", "what_is_new", "requirements") if (extraction.get(k) or {}).get("value"))
    quoted += min(len(users), 2) + min(len(mat["evidence"]), 2)
    s = 5 if quoted >= 6 else 4 if quoted >= 4 else 3 if quoted >= 3 else 2 if quoted >= 1 else 1
    out["dowody"] = {"score": s, "why": f"Potwierdzonych cytatem elementów karty: {quoted}."}

    scored = [(k, v["score"]) for k, v in out.items() if v["score"] is not None]
    total = round(sum(WEIGHTS[k] * v for k, v in scored) / sum(WEIGHTS[k] for k, _ in scored), 2)
    light, verdict = next((name, text) for thr, name, text in THRESHOLDS if total >= thr)
    for k, v in out.items():
        v["dots"] = _dots(v["score"])
    return {
        "criteria": [{"key": k, "label": label, **out[k]} for k, label in CRITERIA],
        "total": total,
        "scored_criteria": len(scored),
        "light": light,
        "light_pl": LIGHT_PL[light],
        "verdict": verdict,
        "method": f"{ASSESS_VERSION}: średnia z ocenionych kryteriów (wagi równe), progi 3,8 / 2,8",
    }


# --- path and recipients ------------------------------------------------------
RECIPIENT_PL = {
    "gmina_miasto": "gminy i miasta",
    "powiat_wojewodztwo": "powiaty i samorządy województw",
    "szkola": "szkoły i placówki oświatowe",
    "uczelnia": "uczelnie",
    "instytut_badawczy": "instytuty badawcze i laboratoria",
    "ochrona_zdrowia": "szpitale i placówki ochrony zdrowia",
    "administracja_sluzby": "administracja i służby (np. policja, straż)",
    "przemysl": "zakłady przemysłowe",
    "msp": "małe i średnie firmy",
    "energetyka_media": "spółki energetyczne i komunalne",
    "transport": "przewoźnicy i przemysł transportowy / lotniczy",
    "rolnictwo": "gospodarstwa i przetwórstwo rolno-spożywcze",
    "ngo": "organizacje pozarządowe",
    "mieszkancy": "mieszkańcy (przez samorząd lub organizacje)",
    "inne": "inni odbiorcy",
}
PUBLIC_RECIPIENTS = {"gmina_miasto", "powiat_wojewodztwo", "szkola", "uczelnia", "ochrona_zdrowia",
                     "administracja_sluzby", "instytut_badawczy"}


def route(record: dict, extraction: dict, mat: dict, scores: dict) -> dict:
    level = mat["level"]
    itype = extraction.get("innovation_type")
    org_types = {o.get("type_hint") for o in record.get("organizations") or []}
    from_science = bool(org_types & {"university", "research_institute"})
    from_company = "company" in org_types and not from_science

    if itype in ("edukacyjna", "społeczna", "organizacyjna"):
        path = "replikacja"
        path_pl = "Przeniesienie modelu do innych instytucji: opis, materiały i szkolenie zespołów u nowych odbiorców."
        metrics = ["liczba instytucji, które przejęły rozwiązanie w ciągu 12 miesięcy",
                   "liczba osób objętych rozwiązaniem u nowych odbiorców"]
    elif level == "exploring":
        path = "dalsze_badania"
        path_pl = "Dalsze prace B+R z partnerem, który chce rozwiązanie przetestować; walidacja poza laboratorium."
        metrics = ["partner do walidacji pozyskany w 6 miesięcy", "zbudowany prototyp lub pilotaż w 12 miesięcy"]
    elif level == "tech_ready" and from_science:
        path = "transfer_technologii"
        path_pl = "Transfer technologii przez centrum transferu uczelni lub instytutu: licencja albo spółka spin-off, pilotaż u pierwszego odbiorcy."
        metrics = ["umowa licencyjna lub spin-off w 12 miesięcy", "pierwszy pilotaż u odbiorcy zewnętrznego"]
    elif level == "tech_ready":
        path = "pilotaz_wdrozeniowy"
        path_pl = "Pilotaż u pierwszego odbiorcy i finansowanie wdrożenia (program wdrożeniowy B+R, fundusze regionalne)."
        metrics = ["pilotaż u odbiorcy w 6 miesięcy", "decyzja o zakupie lub wdrożeniu po pilotażu"]
    elif level == "business_ready":
        path = "skalowanie"
        path_pl = "Skalowanie: kolejni odbiorcy, licencje lub sprzedaż; dla sektora publicznego ścieżka zamówienia lub partnerstwa."
        metrics = ["liczba nowych wdrożeń w 12 miesięcy", "przychód z licencji lub sprzedaży"]
    else:
        path = "zakup_replikacja"
        path_pl = "Rozwiązanie dostępne: informacja dla instytucji z podobnym problemem i ścieżka zakupu lub replikacji."
        metrics = ["liczba instytucji, które zastosowały rozwiązanie", "czas od informacji do decyzji o zakupie"]
    if from_company and path == "transfer_technologii":
        path = "pilotaz_wdrozeniowy"

    recipients = []
    for u in extraction.get("target_users") or []:
        t = u["recipient_type"]
        recipients.append({
            "recipient_type": t,
            "label": RECIPIENT_PL.get(t, t),
            "public_sector": t in PUBLIC_RECIPIENTS,
            "reason": u["who"],
            "quote": u["quote"],
            "catalogue_matches": [],  # filled when Kohesio / Interreg beneficiaries are connected
        })
    pci = sorted(set(extraction.get("sectors") or []) & PCI_PRIORITY_SECTORS)
    return {
        "path": path,
        "path_pl": path_pl,
        "recipients": recipients,
        "pci_priority_sectors": pci,
        "metrics": metrics,
    }


def against(record: dict, extraction: dict, mat: dict, scores: dict) -> list[str]:
    """'Co przemawia przeciw': gaps and risks found by rules (not a second LLM opinion yet)."""
    out = []
    crit = {c["key"]: c for c in scores["criteria"]}
    if crit["koszt_wdrozenia"]["score"] is None:
        out.append("Brak danych o kosztach i wymaganiach wdrożenia: trzeba je ustalić z twórcą.")
    if not extraction.get("target_users"):
        out.append("Źródło nie wymienia odbiorców: kierowanie opiera się tylko na dziedzinie.")
    if not (extraction.get("what_is_new") or {}).get("value"):
        out.append("Tekst nie mówi wprost, co jest nowego względem istniejących rozwiązań.")
    if mat["level"] == "exploring":
        out.append("Brak dowodu działania poza badaniami (prototyp, pilotaż, patent).")
    period = record.get("period") or {}
    end = period.get("end")
    if period.get("status") == "finished" and end and end < "2022":
        out.append(f"Projekt zakończony w {end[:4]} r.: trzeba sprawdzić, czy rozwiązanie jest nadal rozwijane.")
    if extraction.get("is_innovation") != "tak":
        out.append("Model nie potwierdził, że opis przedstawia konkretne rozwiązanie do zastosowania.")
    out.append("Podobne rozwiązania w innych instytucjach: niesprawdzone (etap wyszukiwania podobnych jeszcze niepodłączony).")
    return out
