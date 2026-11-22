"""Implementation agent (`assess`, T027): can this idea be deployed, how, by whom, at what risk, for whom, how good?

1. Agent loop (`radar.pipeline.agent`): the model calls tools (code, no LLM) — similar ideas from the graph,
   regional context (supply per voivodeship x sector, gaps), recipients, internal registry lookup — and returns
   paths / risks / summary. Router order: local CPU model (Bielik) -> cloud -> deterministic rules.
2. Citation check in code: every path, risk, objection and the summary must cite facts the tools returned
   (T1.., rec:<id>, karta, basal); invented ones are sent back once, then dropped.
3. Rule-based baseline from the same facts: fallback and offline mode (demo, tests) with the same shape.
4. Basal recheck validates the result against the data (paths vs maturity, cost vs institution capacity, every
   risk has a mitigation and an owner); violations are fixed or listed as warnings.
5. Reviewer "co przemawia przeciw" (LLM or rules), then weighted, published criteria give the ranking score.
"""

from __future__ import annotations

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
    if any(x.get("closeness", 0) >= 0.1 and x.get("kind") != "possible_duplicate" for x in similar):
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
    # closeness: 0 at the embedder's "similar" threshold, 1 at "near-duplicate" (embed.CALIBRATION)
    near = [x for x in similar if x.get("kind") != "possible_duplicate"]
    top_sim = max((x["similarity"] for x in near), default=0.0)
    top = max((x.get("closeness", 0.0) for x in near), default=None)
    novelty = 5 if top is None else 4 if top < 0.1 else 3 if top < 0.3 else 2 if top < 0.6 else 1
    raw = {"dojrzalosc": 1 + lvl + (1 if lvl == 3 else 0), "przenaszalnosc": min(5, transfer), "skala_problemu": scale,
           "koszt_wdrozenia": cost, "sila_dowodow": evid, "nowosc": novelty}
    why = {
        "dojrzalosc": f"poziom {card.maturity}",
        "przenaszalnosc": ("nietechnologiczna, " if nontech else "") + f"dojrzałość {card.maturity}, koszt {rec.cost_level}",
        "skala_problemu": f"{gaps} województw bez podobnej podaży w sektorze; {len(recipients)} potencjalnych odbiorców",
        "koszt_wdrozenia": label_pl("cost_level", rec.cost_level),
        "sila_dowodow": f"{quotes} cytatów ze źródła" + (", DOI" if rec.doi else "") + (", kwoty" if rec.amounts else ""),
        "nowosc": "brak podobnych rozwiązań w danych" if top is None else
                  f"najbliższe podobne rozwiązanie: podobieństwo {top_sim:.2f} (bliskość {top:.2f} w skali embeddera)",
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


# =========================================================================== entry
def use_llm() -> bool:
    """A real model (local CPU or cloud) is configured; otherwise the deterministic agent runs the same loop."""
    from radar.llm.router import router

    return router().real_available()


def assess(s, rec: Record, card: Card) -> dict:
    """Agent loop with tools -> citation checks -> Basal recheck -> reviewer "what speaks against" -> score."""
    from radar.pipeline import agent as AG

    def baseline(box) -> dict:
        ctx = box.cache.get("ctx") or tool_regional_context(s, rec)
        return {"paths": _paths(rec, card), "risks": _risks(rec, card, ctx, box.cache.get("similar") or [])}

    llm = use_llm()
    deadline = AG.deadline_in() if llm else None  # agent + reviewer share one budget (RADAR_AGENT_BUDGET_S)
    run = AG.run_agent(s, rec, card, baseline, llm, deadline=deadline)
    box = run["toolbox"]
    for name, args in AG.RulePolicy.PLAN:  # scores need every tool's facts, whatever the model chose to call
        if name not in {f["tool"] for f in box.facts.values()}:
            fid, _ = box.run(name, args)
            run["trace"].append({"step": len(run["trace"]) + 1, "tool": name, "args": args, "fact": fid, "by": "reguły (uzupełnienie)"})
    similar, ctx, recipients = box.cache.get("similar") or [], box.cache["ctx"], box.cache.get("recipients") or []
    paths, risks = run["final"]["paths"], run["final"]["risks"]
    if not risks:  # a model that returned no valid risk does not make the idea risk-free
        risks = AG._rules_final(box, {"paths": [], "risks": _risks(rec, card, ctx, similar)})["risks"]
    scores = _scores(rec, card, ctx, similar, recipients)
    a = {"version": VERSION, "paths": paths, "risks": risks, "recipients": recipients, "scores": scores,
         "similar": similar, "regional_context": ctx, "registry": box.cache.get("registry") or [],
         "metrics": _metrics(paths, rec), "summary": run["final"].get("summary"),
         "levels": {"tech_area": label_pl("tech_area", rec.tech_area), "advancement": card.maturity,
                    "cost": label_pl("cost_level", rec.cost_level), "sector": label_pl("sector", rec.sector)},
         "by": run["by"],
         "agent": {"trace": run["trace"], "facts": {k: {"tool": v["tool"], "args": v["args"]} for k, v in run["facts"].items()},
                   "citation_errors": run["errors"][:10], "provider": run["provenance"].get("provider")}}
    a["recheck"] = basal_recheck(a, rec, card) + [f"walidacja cytatów: {e}" for e in run["errors"][:5]]
    a["total"] = total(a["scores"])
    against, rprov, rerr = (AG.llm_review(box, a, deadline=deadline) if llm else (None, {}, []))
    a["against"] = against or AG.rule_review(rec, card, box, scores, risks)
    a["against_by"] = f"LLM {rprov.get('provider')}/{rprov.get('model')}" if against else "reguły"
    if rerr:
        a["recheck"] += [f"recenzent: {e}" for e in rerr[:3]]
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
        "against": ((a.get("against") or [{}])[0]).get("point"),
    }
