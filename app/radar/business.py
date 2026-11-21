"""Business case for an idea, computed by transparent rules (no LLM, microseconds per record, zero infra cost).

Every number carries its assumption so investors, municipalities, universities, schools, startups and individual
inventors see the same logic. Adopter counts come from GUS BDL, for Poland and per voivodeship, via
app/radar/data/adopters.json (written once by scripts/fetch_gus_adopters.py; nothing calls GUS at runtime). Keys the
file does not have fall back to orders of magnitude from public statistics, labelled "szacunek".
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from radar.basal import taxonomy as T
from radar.basal.classifier import label_pl
from radar.basal.embed import fold

LEVELS = ["exploring", "tech_ready", "business_ready", "market_ready"]
# probability that the idea reaches deployment, by evidence-based maturity (risk discount)
SUCCESS_P = {"exploring": .10, "tech_ready": .30, "business_ready": .60, "market_ready": .85}
# one deployment's value for the adopter (PLN), mid-points of the cost bands used by Basal
UNIT_PLN = {"niski": 60_000, "sredni": 600_000, "wysoki": 6_000_000, "bardzo_wysoki": 30_000_000}
# Fallback when app/radar/data/adopters.json has no such key: orders of magnitude (GUS 2024, RSPO, POL-on), "szacunek"
ADOPTERS = {
    "gminy": (2_477, "gmin (GUS)"),
    "powiaty": (380, "powiatów i miast na prawach powiatu"),
    "szkoly": (21_000, "szkół podstawowych i ponadpodstawowych (RSPO)"),
    "przedszkola": (22_000, "placówek wychowania przedszkolnego"),
    "uczelnie": (350, "uczelni (POL-on)"),
    "instytuty": (110, "instytutów badawczych i PAN"),
    "szpitale": (950, "szpitali"),
    "biblioteki": (7_700, "bibliotek publicznych"),
    "msp_sektor": (40_000, "firm w sektorze (MŚP, szacunek z REGON)"),
    "przemysl": (8_000, "zakładów przemysłowych w branży"),
    "energetyka": (1_200, "przedsiębiorstw energetycznych i ciepłowni"),
    "firmy_ict": (40_000, "firm ICT (MŚP, szacunek z REGON)"),
    "firmy_rolnictwo": (40_000, "gospodarstw i firm rolnych (szacunek z REGON)"),
    "firmy_budownictwo": (40_000, "firm budowlanych (MŚP, szacunek z REGON)"),
}
ADOPTERS_FILE = Path(__file__).parent / "data" / "adopters.json"
BY_INNOVATION = {"edukacyjna": "szkoly", "spoleczna": "gminy", "organizacyjna": "gminy", "uslugowa": "gminy", "procesowa": "gminy"}
BY_SECTOR = {"Q_zdrowie": "szpitale", "P_edukacja": "szkoly", "O_administracja": "gminy", "H_transport": "gminy",
             "E_srodowisko": "gminy", "D_energetyka": "energetyka", "C_przemysl": "przemysl", "M_nauka": "uczelnie",
             "R_kultura": "biblioteki", "J_ict": "firmy_ict", "A_rolnictwo": "firmy_rolnictwo", "F_budownictwo": "firmy_budownictwo"}
ADOPTION_3Y = {"niski": .05, "sredni": .02, "wysoki": .008, "bardzo_wysoki": .003}  # realistic 3-year uptake
REVENUE_MULTIPLE = 3.0  # licence / spin-off value ≈ 3x expected yearly revenue (conservative early-stage multiple)
ROYALTY = .05  # typical university licence royalty on adopter spend
COPY_CAP_PLN = 2_000_000  # a copied, already working solution rarely costs an adopter more than this
VALUE_CAP_PLN = 50_000_000  # early-stage licence/spin-off values above this are not credible without due diligence

FUNDING = [  # (programme, who, when it fits)
    ("FENG — Ścieżka SMART", "firmy i konsorcja z uczelniami", lambda r, lvl: r.innovation_type == "technologiczna" and lvl >= 1),
    ("NCBR LIDER / Lider", "młodzi naukowcy", lambda r, lvl: r.institution_type in ("uczelnia", "instytut") and lvl <= 1),
    ("Horyzont Europa (EIC Pathfinder / Transition)", "zespoły badawcze, startupy deep-tech", lambda r, lvl: r.innovation_type == "technologiczna"),
    ("FERS — innowacje społeczne", "JST, NGO, szkoły", lambda r, lvl: r.innovation_type in ("spoleczna", "edukacyjna", "organizacyjna")),
    ("FEnIKS — środowisko i energia", "JST, przedsiębiorstwa", lambda r, lvl: r.sector in ("D_energetyka", "E_srodowisko")),
    ("Fundusze Europejskie dla Podkarpacia 2021–2027", "podmioty z regionu", lambda r, lvl: r.voivodeship == "podkarpackie"),
    ("Programy regionalne FE 2021–2027", "JST i firmy w województwie", lambda r, lvl: bool(r.voivodeship) and r.voivodeship != "podkarpackie"),
    ("Akcelerator / Inkubator PCI", "młodzi innowatorzy 16–30, startupy", lambda r, lvl: lvl <= 2),
    ("Interreg (współpraca transgraniczna)", "JST, uczelnie", lambda r, lvl: r.innovation_type in ("organizacyjna", "spoleczna", "uslugowa")),
    ("Partnerstwo publiczno-prywatne / zamówienie przedkomercyjne (PCP)", "JST z firmą", lambda r, lvl: r.cost_level in ("wysoki", "bardzo_wysoki") and lvl >= 1),
]


PROGRAMME = re.compile(r"^(program priorytetowy|program operacyjny|regionalny program)")


@lru_cache(maxsize=4)
def load_adopters(path: Path | None = None) -> dict:
    """The GUS file, or {} when it is missing or unreadable (the estimates above are used then)."""
    p = Path(path or ADOPTERS_FILE)
    try:
        doc = json.loads(p.read_text("utf-8"))
    except (OSError, ValueError):
        return {}
    return doc if isinstance(doc.get("adopters"), dict) else {}


def adopters_for(key: str, voivodeship: str | None = None) -> dict:
    """Potential adopters of one kind: in Poland and, when the record has a voivodeship, in that region.

    From GUS BDL when adopters.json has the key (with year, variable ids and fetch date), else the estimate."""
    doc = load_adopters(ADOPTERS_FILE)
    g = (doc.get("adopters") or {}).get(key)
    woj = fold(voivodeship or "").strip() or None
    if g and g.get("poland"):
        by_woj = {fold(k): v for k, v in (g.get("by_voivodeship") or {}).items()}
        regional = by_woj.get(woj) if woj else None
        fetched = (g.get("fetched_at") or doc.get("fetched_at") or "")[:10]
        return {"count": int(g["poland"]), "who": f"{g['label']} (GUS BDL, {g['year']})", "key": key,
                "regional": regional if regional is not None else (round(g["poland"] / 16) if woj else None),
                "regional_exact": regional is not None, "voivodeship": voivodeship if woj else None,
                "source": "GUS BDL", "year": g.get("year"), "fetched_at": fetched,
                "variable_ids": g.get("variable_ids") or [g.get("variable_id")]}
    n, label = ADOPTERS[key]
    return {"count": n, "who": label, "key": key, "regional": round(n / 16) if woj else None, "regional_exact": False,
            "voivodeship": voivodeship if woj else None, "source": "szacunek", "year": None, "fetched_at": None,
            "variable_ids": []}


def is_infrastructure(rec) -> bool:
    """The Basal rule (taxonomy.INFRASTRUCTURE); kept here for records Basal saw before the rule existed."""
    return T.is_infrastructure(rec.title, rec.abstract)


def dedup_key(rec) -> str:
    """One card per programme/title: "Czyste Powietrze w woj. X" and "... w woj. Y" collapse into one."""
    t = fold(rec.title or "")
    t = re.sub(r"\b(w|we) (wojewodztwie|woj\.?) \w+(-\w+)?", "", t)
    return re.sub(r"[^a-z0-9]+", " ", t).strip()[:80]


SPECIFIC_SECTORS = {"Q_zdrowie", "P_edukacja", "M_nauka", "D_energetyka", "C_przemysl", "R_kultura"}


def adopter_key(rec) -> str:
    """Who buys it: a specific sector wins (a hospital system is for hospitals, not municipalities)."""
    if rec.sector in SPECIFIC_SECTORS:
        return BY_SECTOR[rec.sector]
    return BY_INNOVATION.get(rec.innovation_type or "") or BY_SECTOR.get(rec.sector or "", "msp_sektor")


def business_case(rec, card) -> dict:
    lvl_name = card.maturity or "exploring"
    lvl = LEVELS.index(lvl_name) if lvl_name in LEVELS else 0
    cost = rec.cost_level or "sredni"
    unit = UNIT_PLN.get(cost, 600_000)
    amounts = [v for v in (rec.amounts or {}).values() if isinstance(v, (int, float)) and v > 0]
    # a recorded project budget is the cost of the original build, not of a copy: a copy costs ~30% of it
    deploy_cost = min(COPY_CAP_PLN, min(unit, max(amounts) * .3) if amounts else unit)
    key = adopter_key(rec)
    a = adopters_for(key, rec.voivodeship)
    n = a["count"]
    tam = n * deploy_cost
    # one region first: the region's own GUS count, or 1/16 of the country when only an estimate is known
    sam = a["regional"] * deploy_cost if a["regional"] is not None else tam
    som_3y = n * ADOPTION_3Y.get(cost, .02) * deploy_cost
    p = SUCCESS_P[lvl_name]
    yearly_rev = som_3y / 3
    licence_value = min(VALUE_CAP_PLN, yearly_rev * REVENUE_MULTIPLE * p)
    royalty_3y = som_3y * ROYALTY * p
    own_build = deploy_cost * 3  # building the same thing from scratch in another institution
    funding = [{"programme": prog, "for": who} for prog, who, fits in FUNDING if fits(rec, lvl)][:4]
    model = ("licencja / sprzedaż" if rec.innovation_type == "technologiczna" else "transfer modelu działania + szkolenie")
    return {
        "version": "business/v1",
        "adopters": a,
        "deploy_cost_pln": round(deploy_cost),
        "market": {"tam_pln": round(tam), "sam_pln": round(sam), "som_3y_pln": round(som_3y),
                   "adoption_3y": ADOPTION_3Y.get(cost, .02)},
        "valuation": {"success_probability": p, "licence_or_spinoff_pln": round(licence_value),
                      "royalty_3y_pln": round(royalty_3y), "multiple": REVENUE_MULTIPLE},
        "savings_per_adopter_pln": round(own_build - deploy_cost),
        "payback": "< 1 rok" if cost == "niski" else "1–2 lata" if cost == "sredni" else "3–5 lat",
        "model": model,
        "funding": funding,
        "assumptions": [
            _adopters_line(a),
            f"koszt wdrożenia u odbiorcy: {round(deploy_cost):,} zł ({'30% budżetu projektu' if amounts else 'środek przedziału kosztu ' + label_pl('cost_level', cost)})".replace(",", " "),
            f"realna adopcja w 3 lata: {ADOPTION_3Y.get(cost, .02):.1%} odbiorców",
            f"szansa wdrożenia przy dojrzałości „{lvl_name}”: {p:.0%}",
            f"wartość licencji/spin-off: {REVENUE_MULTIPLE:g}× roczny przychód × szansa wdrożenia (maks. 50 mln zł); tantiemy {ROYALTY:.0%}",
            "koszt kopii u odbiorcy: maks. 2 mln zł (gotowe rozwiązanie, nie budowa od zera)",
            "własne opracowanie od zera ≈ 3× koszt wdrożenia gotowego rozwiązania",
        ],
    }


def _adopters_line(a: dict) -> str:
    n = f"{a['count']:,}".replace(",", " ")
    if a["source"] == "szacunek":
        line = f"odbiorcy: {n} {a['who']} (szacunek)"
    else:
        ids = ", ".join(str(i) for i in a["variable_ids"] if i)
        line = f"odbiorcy: {n} {a['who']}; zmienne BDL {ids}, pobrano {a['fetched_at']}"
    if a["voivodeship"]:
        r = f"{a['regional']:,}".replace(",", " ")
        line += (f"; w województwie {a['voivodeship']}: {r}" if a["regional_exact"]
                 else f"; region ≈ 1/16 kraju ({r})")
    return line


# -------------------------------------------------------------------- audiences (one page, six lenses)
PERSONAS = {
    "inwestorzy": {"name": "Inwestorzy i firmy", "icon": "trending-up",
                   "promise": "Technologie z polskich uczelni i instytutów z gotowym prototypem lub patentem, z wyceną i ścieżką licencji albo spin-offu.",
                   "filters": {"innovation_type": "technologiczna", "maturity": "tech_ready,business_ready,market_ready", "cost_level": "niski,sredni,wysoki"},
                   "metric": "licence_or_spinoff_pln", "cta": "Umów rozmowę z twórcą przez PCI", "skip_sources": ["kohesio-projekty", "demo-kohesio"]},
    "samorzady": {"name": "Samorządy i instytucje publiczne", "icon": "landmark",
                  "promise": "Rozwiązania, które już działają w innej gminie: z kosztem wdrożenia, oszczędnością i źródłem finansowania.",
                  "filters": {"innovation_type": "organizacyjna,spoleczna,uslugowa,procesowa", "maturity": "business_ready,market_ready", "cost_level": "niski,sredni,wysoki"},
                  "metric": "savings_per_adopter_pln", "cta": "Chcę to u siebie"},
    "uczelnie": {"name": "Uczelnie i jednostki naukowe", "icon": "graduation-cap",
                 "promise": "Wyniki badań z potencjałem wdrożenia: kto potrzebuje, jaka wartość licencji, jaki grant na następny krok.",
                 "filters": {"institution_type": "uczelnia,instytut"},
                 "metric": "royalty_3y_pln", "cta": "Zgłoś do komercjalizacji", "skip_sources": ["kohesio-projekty", "demo-kohesio"]},
    "szkoly": {"name": "Szkoły i placówki edukacyjne", "icon": "school",
               "promise": "Sprawdzone programy i narzędzia z innych szkół, tanie do powielenia, z gotowym pierwszym krokiem.",
               "filters": {"innovation_type": "edukacyjna", "cost_level": "niski,sredni"},
               "metric": "savings_per_adopter_pln", "cta": "Wdróż w swojej szkole"},
    "startupy": {"name": "Startupy i przedsiębiorstwa", "icon": "rocket",
                 "promise": "Rynki z popytem publicznym i technologie do licencjonowania: TAM, odbiorcy i partnerzy naukowi.",
                 "filters": {"maturity": "tech_ready,business_ready", "cost_level": "niski,sredni,wysoki"},
                 "metric": "som_3y_pln", "cta": "Znajdź partnera", "skip_sources": ["kohesio-projekty", "demo-kohesio"]},
    "innowatorzy": {"name": "Indywidualni innowatorzy i wynalazcy", "icon": "lightbulb",
                    "promise": "Sprawdź, czy ktoś już to zrobił, ile to może być warte i skąd wziąć pieniądze na prototyp.",
                    "filters": {}, "metric": "licence_or_spinoff_pln", "cta": "Sprawdź swój pomysł", "skip_sources": ["kohesio-projekty", "demo-kohesio"]},
}


def metric_value(bc: dict, metric: str) -> float:
    for part in (bc.get("valuation", {}), bc.get("market", {}), bc):
        if metric in part:
            return part[metric]
    return 0
