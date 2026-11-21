"""Implementation agent (`assess`): can this idea be deployed, how, by whom, at what risk, for whom, and how good is it?

1. Tools (code, no LLM) gather facts: similar ideas (graph), regional context (supply per voivodeship x sector,
   gaps), recipients (institutions in the data + recipient types), Basal labels.
2. A rule-based baseline Assessment is always built from those facts (works offline, demo mode, tests).
3. If a real LLM is configured (cloud or the local CPU model), it rewrites paths / risks / mitigations in plain
   Polish using ONLY the tool facts; its output must keep the schema.
4. Basal recheck validates the result against the data (paths vs maturity, cost vs institution capacity, every
   risk has a mitigation and an owner); violations are fixed or listed as warnings.
5. Weighted, published criteria give the total score used for ranking.
"""

from __future__ import annotations

import json
from collections import Counter

from sqlalchemy import func, select

from radar.basal import graph
from radar.basal import taxonomy as T
from radar.basal.classifier import label_pl
from radar.models import Card, Record

VERSION = "assess/v1"
LEVELS = ["exploring", "tech_ready", "business_ready", "market_ready"]
CRITERIA = {  # name: (weight, Polish description) — shown in the UI as the transparent rubric
    "dojrzalosc": (0.20, "jak blisko wdrożenia jest rozwiązanie (dowody: publikacja → prototyp/patent → wdrożenie)"),
    "przenaszalnosc": (0.20, "czy inna instytucja może to przejąć bez twórcy"),
    "skala_problemu": (0.15, "ilu potencjalnych odbiorców ma ten sam problem"),
    "koszt_wdrozenia": (0.15, "im taniej wdrożyć u odbiorcy, tym wyżej"),
    "sila_dowodow": (0.15, "kompletność i wiarygodność danych źródłowych"),
    "nowosc": (0.15, "czy podobne rozwiązania już istnieją gdzie indziej"),
}
PUBLIC = ("szkola", "uczelnia", "instytut", "jst", "inna_publiczna")
RECIPIENT_TYPES = {  # innovation_type / sector -> who typically adopts it
    "edukacyjna": ["szkoły podstawowe i średnie", "organy prowadzące szkoły (gminy, powiaty)", "kuratoria i ośrodki doskonalenia nauczycieli"],
    "spoleczna": ["gminy i miejskie/gminne ośrodki pomocy społecznej", "centra usług społecznych", "organizacje pozarządowe"],
    "organizacyjna": ["urzędy gmin i miast", "starostwa powiatowe", "jednostki organizacyjne samorządu"],
    "procesowa": ["urzędy i instytucje publiczne o podobnych procedurach", "uczelnie (administracja)"],
    "uslugowa": ["gminy wiejskie i miejsko-wiejskie", "centra usług społecznych", "operatorzy usług publicznych"],
    "technologiczna": ["firmy z sektora (MŚP i duże)", "parki i inkubatory technologiczne", "centra transferu technologii uczelni"],
}


# =========================================================================== tools
def tool_similar(s, rec: Record) -> list[dict]:
    return graph.similar(s, rec, k=5)


def tool_regional_context(s, rec: Record) -> dict:
    """Supply of ideas per voivodeship for this sector; gap = voivodeships with fewer ideas than average."""
    rows = s.execute(select(Record.voivodeship, Record.sector, func.count()).where(Record.status.in_(graph.INDEXED))
                     .group_by(Record.voivodeship, Record.sector)).all()
    by_v = Counter()
    sector_by_v = Counter()
    for v, sec, n in rows:
        if v:
            by_v[v] += n
            if sec == rec.sector:
                sector_by_v[v] += n
    all_v = list(T.VOIVODESHIPS.values())
    avg = (sum(sector_by_v.values()) / len(all_v)) if all_v else 0
    gaps = sorted([v for v in all_v if sector_by_v.get(v, 0) < max(avg, 0.5) and v != rec.voivodeship])
    return {
        "voivodeship": rec.voivodeship,
        "sector": rec.sector, "sector_pl": label_pl("sector", rec.sector),
        "ideas_in_region_sector": sector_by_v.get(rec.voivodeship, 0) if rec.voivodeship else None,
        "national_avg_per_region": round(avg, 2),
        "regions_without_supply": gaps,
        "is_regional_specialisation": rec.voivodeship == "podkarpackie" and rec.tech_area in
        ("lotnictwo_kosmos", "motoryzacja", "oprogramowanie_euslugi", "ai_dane", "biotech_medtech"),
    }


def tool_recipients(s, rec: Record, similar: list[dict]) -> list[dict]:
    out = []
    for t in RECIPIENT_TYPES.get(rec.innovation_type or "", RECIPIENT_TYPES["technologiczna"])[:3]:
        out.append({"name": t, "kind": "typ odbiorcy", "why": f"typowi odbiorcy innowacji typu „{label_pl('innovation_type', rec.innovation_type)}”"})
    # concrete institutions from the data: same sector or tech area, other organisation
    def core(name: str) -> str:  # "Politechnika Rzeszowska, Wydział X" ~ "Politechnika Rzeszowska im. I. Ł." (until T023)
        from radar.basal.embed import fold

        return " ".join(fold(name.split(",")[0]).split()[:2])

    own = {core(seg) for a in rec.affiliations or [] for seg in a.split(",") if seg.strip()}
    # "metody_nietech" is too broad to match on alone: then the sector must match
    match = (Record.sector == rec.sector) if rec.tech_area in (None, "metody_nietech") else \
        ((Record.sector == rec.sector) | (Record.tech_area == rec.tech_area))
    q = select(Record).where(Record.id != rec.id, Record.status.in_(graph.INDEXED), match).limit(30)
    seen = set()
    for r in s.scalars(q):
        for a in r.affiliations or []:
            if any(core(seg) in own for seg in a.split(",") if seg.strip()) or core(a) in seen:
                continue
            seen.add(core(a))
            why = []
            if r.sector == rec.sector:
                why.append(f"działa w sektorze {label_pl('sector', r.sector)}")
            if r.tech_area == rec.tech_area:
                why.append(f"pracuje w obszarze {label_pl('tech_area', r.tech_area)}")
            if r.voivodeship and r.voivodeship != rec.voivodeship:
                why.append(f"województwo {r.voivodeship} (transfer poza region twórcy)")
            out.append({"name": a, "kind": "instytucja z danych", "record_id": r.id, "why": "; ".join(why)})
            if len(out) >= 7:
                return out
    return out


# =========================================================================== baseline
def _paths(rec: Record, card: Card) -> list[dict]:
    lvl = card.maturity or "exploring"
    tech = (rec.innovation_type == "technologiczna")
    P = []
    if lvl == "exploring":
        P.append({"path": "rozwój", "why": "rozwiązanie na etapie badań: potrzebny prototyp i partner",
                  "steps": [{"step": "zweryfikować wynik w warunkach zbliżonych do rzeczywistych (prototyp, pilotaż)", "who": "twórca / zespół badawczy", "time": "3–12 mies."},
                            {"step": "złożyć wniosek o grant (NCBR, NCN, FENG) z partnerem przemysłowym lub JST", "who": "twórca + centrum transferu technologii", "time": "2–4 mies."},
                            {"step": "udostępnić laboratoria i mentoring", "who": "PCI", "time": "od razu"}]})
    if lvl in ("tech_ready", "business_ready") and tech:
        P.append({"path": "komercjalizacja", "why": "jest prototyp, pilotaż albo patent, brak sprzedaży poza twórcą",
                  "steps": [{"step": "ocenić ochronę własności intelektualnej (zgłoszenie patentowe, know-how)", "who": "centrum transferu technologii", "time": "1–2 mies."},
                            {"step": "wybrać model: licencja dla firmy z sektora albo spin-off", "who": "uczelnia / instytut + inwestor", "time": "3–6 mies."},
                            {"step": "skojarzyć z firmami i funduszami (akcelerator PCI)", "who": "PCI", "time": "1–3 mies."}]})
    if lvl in ("tech_ready", "business_ready", "market_ready") and not tech:
        P.append({"path": "wdrożenie w innej organizacji (transfer)", "why": "rozwiązanie działa u twórcy i nie wymaga nowej technologii",
                  "steps": [{"step": "spisać model działania: procedura, role, koszty, umowy (paszport transferu)", "who": "twórca (instytucja macierzysta)", "time": "1 mies."},
                            {"step": "znaleźć 2–3 instytucje z tym samym problemem i zaprosić na wizytę studyjną", "who": "PCI + odbiorca", "time": "1–2 mies."},
                            {"step": "pilotaż u odbiorcy z opiekunem od twórcy", "who": "odbiorca (np. gmina) + twórca", "time": "3–6 mies."}]})
    if lvl == "tech_ready" and not tech:
        P.append({"path": "pilotaż", "why": "opisany pilotaż — warto go powtórzyć w innym miejscu przed skalowaniem",
                  "steps": [{"step": "uzgodnić pilotaż z jedną instytucją o innym profilu", "who": "PCI + odbiorca", "time": "1–2 mies."}]})
    if lvl in ("business_ready", "market_ready") and tech:
        P.append({"path": "skalowanie i finansowanie", "why": "wdrożone u twórcy; kolejny krok to rynek lub inni odbiorcy",
                  "steps": [{"step": "przygotować ofertę dla odbiorców i model finansowania (dotacja, zamówienie przedkomercyjne)", "who": "twórca + PCI", "time": "2–4 mies."}]})
    return P or [{"path": "rozwój", "why": "domyślnie", "steps": [{"step": "uzupełnić opis i dowody", "who": "twórca", "time": "1 mies."}]}]


def _risks(rec: Record, card: Card, ctx: dict, similar: list[dict]) -> list[dict]:
    R = []
    if rec.innovation_type == "technologiczna" and rec.kind != "patent":
        R.append({"risk": "brak ochrony własności intelektualnej (brak śladu patentu)", "level": "średnie",
                  "mitigation": "przegląd stanu techniki i decyzja o zgłoszeniu patentowym przed publiczną prezentacją", "owner": "centrum transferu technologii"})
    if rec.cost_level in ("wysoki", "bardzo_wysoki"):
        R.append({"risk": "wysoki koszt wdrożenia u odbiorcy", "level": "wysokie" if rec.cost_level == "bardzo_wysoki" else "średnie",
                  "mitigation": "montaż finansowy: fundusze europejskie, partnerstwo kilku odbiorców, etapowanie", "owner": "odbiorca + PCI"})
    if rec.institution_type == "szkola":
        R.append({"risk": "ograniczony czas i zasoby twórców w szkole na wsparcie transferu", "level": "średnie",
                  "mitigation": "materiały „zrób to sam” i jedna sesja szkoleniowa nagrana dla kolejnych szkół", "owner": "PCI"})
    if rec.institution_type == "jst" or rec.innovation_type in ("spoleczna", "organizacyjna", "uslugowa"):
        R.append({"risk": "zamówienia publiczne i procedury u odbiorcy wydłużają wdrożenie", "level": "średnie",
                  "mitigation": "wzór dokumentacji (opis przedmiotu zamówienia, porozumienie międzygminne)", "owner": "twórca + odbiorca"})
    if rec.sector in ("J_ict", "O_administracja", "Q_zdrowie") or rec.tech_area == "oprogramowanie_euslugi":
        R.append({"risk": "przetwarzanie danych osobowych (RODO), bezpieczeństwo systemu", "level": "średnie",
                  "mitigation": "ocena skutków (DPIA), umowa powierzenia, minimalizacja danych", "owner": "odbiorca (administrator danych)"})
    if (card.maturity or "exploring") == "exploring":
        R.append({"risk": "brak dowodu działania poza laboratorium", "level": "wysokie",
                  "mitigation": "pilotaż w kontrolowanych warunkach przed rozmowami z odbiorcami", "owner": "twórca"})
    if any(x["similarity"] >= 0.35 and x.get("kind") != "possible_duplicate" for x in similar):
        R.append({"risk": "podobne rozwiązania już istnieją — ryzyko dublowania prac", "level": "średnie",
                  "mitigation": "porównać z podobnymi kartami i połączyć zespoły zamiast budować drugi raz", "owner": "PCI"})
    if (card.provenance or {}).get("provider") == "mock":
        R.append({"risk": "pola karty wyciągnięte heurystyką (bez modelu językowego)", "level": "niskie",
                  "mitigation": "operator sprawdza cytaty przed zatwierdzeniem", "owner": "operator PCI"})
    return R


def _scores(rec: Record, card: Card, ctx: dict, similar: list[dict], recipients: list[dict]) -> dict:
    lvl = LEVELS.index(card.maturity or "exploring")
    nontech = rec.innovation_type in ("organizacyjna", "edukacyjna", "spoleczna", "procesowa", "uslugowa")
    transfer = 2 + (1 if nontech else 0) + (1 if lvl >= 2 else 0) + (1 if rec.cost_level in ("niski", "sredni") else 0)
    gaps = len(ctx.get("regions_without_supply") or [])
    scale = 1 + min(4, round(gaps / 4) + (1 if len([r for r in recipients if r["kind"] == "instytucja z danych"]) >= 2 else 0))
    cost = {"niski": 5, "sredni": 4, "wysoki": 2, "bardzo_wysoki": 1}.get(rec.cost_level or "sredni", 3)
    quotes = sum(1 for e in (card.evidence or {}).values() if e and e.get("quote"))
    evid = min(5, 1 + quotes // 2 + (1 if rec.doi or rec.kind == "patent" else 0) + (1 if rec.amounts else 0))
    top_sim = max((x["similarity"] for x in similar if x.get("kind") != "possible_duplicate"), default=0.0)
    novelty = 5 if top_sim < 0.2 else 4 if top_sim < 0.3 else 3 if top_sim < 0.4 else 2 if top_sim < 0.55 else 1
    raw = {"dojrzalosc": 1 + lvl + (1 if lvl == 3 else 0), "przenaszalnosc": min(5, transfer), "skala_problemu": scale,
           "koszt_wdrozenia": cost, "sila_dowodow": evid, "nowosc": novelty}
    why = {
        "dojrzalosc": f"poziom {card.maturity}",
        "przenaszalnosc": ("nietechnologiczna, " if nontech else "") + f"dojrzałość {card.maturity}, koszt {rec.cost_level}",
        "skala_problemu": f"{gaps} województw bez podobnej podaży w sektorze; {len(recipients)} potencjalnych odbiorców",
        "koszt_wdrozenia": label_pl("cost_level", rec.cost_level),
        "sila_dowodow": f"{quotes} cytatów ze źródła" + (", DOI" if rec.doi else "") + (", kwoty" if rec.amounts else ""),
        "nowosc": f"najbliższe podobne rozwiązanie: podobieństwo {top_sim:.2f}",
    }
    return {k: {"score": max(0, min(5, int(v))), "why": why[k]} for k, v in raw.items()}


def _metrics(paths: list[dict], rec: Record) -> list[str]:
    m = ["liczba instytucji, które wdrożyły rozwiązanie w ciągu 12 mies. od karty (cel: ≥ 2)",
         "czas od zatwierdzenia karty do pierwszej rozmowy z odbiorcą (cel: ≤ 30 dni)"]
    names = {p["path"] for p in paths}
    if "komercjalizacja" in names:
        m.append("podpisana licencja albo założona spółka w 12 mies.")
    if "rozwój" in names:
        m.append("złożony wniosek o finansowanie B+R w 6 mies.")
    if any("transfer" in n for n in names):
        m.append("liczba użytkowników końcowych u nowych odbiorców (np. mieszkańców, uczniów)")
    if rec.amounts:
        m.append("kwota środków pozyskanych na wdrożenie u odbiorców")
    return m


# =========================================================================== recheck (Basal, again)
def basal_recheck(a: dict, rec: Record, card: Card) -> list[str]:
    warn = []
    lvl = card.maturity or "exploring"
    for p in a["paths"]:
        if p["path"] == "komercjalizacja" and lvl == "exploring":
            warn.append("komercjalizacja przy dojrzałości „badania” — przesunięto na ścieżkę rozwoju")
            p["path"] = "rozwój"
        if not p.get("steps"):
            warn.append(f"ścieżka {p['path']} bez kroków")
        for st in p.get("steps", []):
            st.setdefault("who", "do ustalenia")
    for r in a["risks"]:
        if not r.get("mitigation"):
            r["mitigation"] = "do ustalenia z twórcą"
            warn.append(f"ryzyko „{r['risk']}” bez mitygacji")
        r.setdefault("owner", "do ustalenia")
    if rec.cost_level in ("wysoki", "bardzo_wysoki") and rec.institution_type == "szkola":
        warn.append("koszt wysoki jak na szkołę — wymagany partner finansujący")
    if not a["recipients"]:
        warn.append("brak odbiorców — karta do uzupełnienia")
    for k, v in a["scores"].items():
        v["score"] = max(0, min(5, int(v["score"])))
    return warn


def total(scores: dict) -> float:
    return round(sum(CRITERIA[k][0] * v["score"] for k, v in scores.items() if k in CRITERIA) / 5 * 100, 1)


# =========================================================================== LLM refinement
SYSTEM = """Jesteś analitykiem wdrożeń innowacji w Podkarpackim Centrum Innowacji. Dostajesz FAKTY (wynik narzędzi)
i WERSJĘ ROBOCZĄ oceny. Popraw tylko: "paths" (kroki: kto co robi i kiedy), "risks" (ryzyko, poziom, mitygacja,
właściciel) i "summary". Nie dodawaj faktów spoza FAKTÓW, nie zmieniaj ocen liczbowych. Odpowiedz WYŁĄCZNIE JSON
{"paths":[...], "risks":[...], "summary":"..."} w tym samym kształcie co wersja robocza, po polsku."""


def _llm_available() -> bool:
    from radar.llm.router import router

    return any(p.name != "mock" and p.available() for p in router().providers)


def llm_refine(facts: dict, draft: dict) -> tuple[dict | None, dict]:
    from radar.llm.router import AllProvidersFailed, router

    try:
        out, prov = router().complete_json(SYSTEM, "FAKTY:\n" + json.dumps(facts, ensure_ascii=False, default=str)[:6000]
                                           + "\n\nWERSJA ROBOCZA:\n" + json.dumps(draft, ensure_ascii=False)[:4000])
    except AllProvidersFailed as e:
        return None, {"error": str(e)}
    if prov.get("provider") == "mock" or not isinstance(out.get("paths"), list) or not isinstance(out.get("risks"), list):
        return None, prov
    return out, prov


# =========================================================================== entry
def assess(s, rec: Record, card: Card) -> dict:
    similar = tool_similar(s, rec)
    ctx = tool_regional_context(s, rec)
    recipients = tool_recipients(s, rec, similar)
    paths = _paths(rec, card)
    risks = _risks(rec, card, ctx, similar)
    scores = _scores(rec, card, ctx, similar, recipients)
    a = {"version": VERSION, "paths": paths, "risks": risks, "recipients": recipients, "scores": scores,
         "similar": similar, "regional_context": ctx, "metrics": _metrics(paths, rec),
         "levels": {"tech_area": label_pl("tech_area", rec.tech_area), "advancement": card.maturity,
                    "cost": label_pl("cost_level", rec.cost_level), "sector": label_pl("sector", rec.sector)},
         "by": "reguły"}
    if _llm_available():
        facts = {"karta": {"nazwa": card.solution_name, "problem": card.problem_solved, "co_nowego": card.what_is_new},
                 "basal": {k: (rec.basal or {}).get(k, {}).get("value") for k in ("sector", "tech_area", "innovation_type", "institution_type", "cost_level", "voivodeship")},
                 "podobne": similar, "region": ctx, "odbiorcy": recipients}
        refined, prov = llm_refine(facts, {"paths": paths, "risks": risks})
        if refined:
            a["paths"], a["risks"] = refined["paths"], refined["risks"]
            a["summary"] = refined.get("summary")
            a["by"] = f"LLM {prov.get('provider')}/{prov.get('model')} na faktach z narzędzi"
    a["recheck"] = basal_recheck(a, rec, card)
    a["total"] = total(a["scores"])
    a["criteria"] = {k: {"weight": w, "what": d} for k, (w, d) in CRITERIA.items()}
    return a


def brief(rec: Record, card: Card, a: dict) -> dict:
    """One-page brief for the reels feed: deterministic, no new facts."""
    first = a["paths"][0] if a["paths"] else {}
    return {
        "hook": card.problem_solved or rec.title,
        "solution": card.solution_name or rec.title,
        "summary": a.get("summary") or card.summary_pl,
        "who": ", ".join((rec.affiliations or [])[:2]) or label_pl("institution_type", rec.institution_type),
        "where": rec.voivodeship,
        "tags": [label_pl("sector", rec.sector), label_pl("tech_area", rec.tech_area), label_pl("innovation_type", rec.innovation_type)],
        "maturity": card.maturity, "cost": label_pl("cost_level", rec.cost_level),
        "for_whom": [r["name"] for r in a["recipients"][:3]],
        "next_step": (first.get("steps") or [{}])[0].get("step") if first else None,
        "path": first.get("path"),
        "score": a["total"],
        "top_criteria": sorted(((k, v["score"]) for k, v in a["scores"].items()), key=lambda kv: -kv[1])[:3],
        "metric": (a.get("metrics") or [None])[0],
    }
