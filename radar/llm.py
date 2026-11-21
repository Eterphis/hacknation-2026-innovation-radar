"""Extraction providers behind one interface (D-003: swappable LLM with fallback).

* ClaudeExtractor  - Claude via the official `anthropic` SDK (optional dependency, `pip install anthropic`),
                     structured outputs constrained to EXTRACTION_SCHEMA.
* RulesExtractor   - deterministic, offline. Same output shape, quotes are whole source sentences.
                     Keeps the demo working with no key and is the last fallback.

Choose with RADAR_LLM=auto|claude|offline (default auto: Claude when the SDK and a credential are present).
"""

from __future__ import annotations

import json
import os
import re

from .extract import EXTRACTION_SCHEMA, SYSTEM_PROMPT, Extractor, LLMError
from .text import fold

CLAUDE_MODEL = os.environ.get("RADAR_CLAUDE_MODEL", "claude-opus-5-5")


# --- Claude ------------------------------------------------------------------
class ClaudeExtractor:
    name = "claude"

    def __init__(self, model: str = CLAUDE_MODEL, client=None, effort: str = "medium") -> None:
        if client is None:
            try:
                import anthropic  # optional dependency
            except ImportError as e:  # pragma: no cover - depends on the machine
                raise LLMError("pakiet anthropic nie jest zainstalowany (pip install anthropic)") from e
            client = anthropic.Anthropic()
        self.client = client
        self.model = model
        self.effort = effort

    def extract(self, source_text: str, record: dict, feedback: list[str] | None = None) -> dict:
        user = f"Tekst źródłowy (źródło: {record.get('source_name')}, {record.get('url')}):\n\n<zrodlo>\n{source_text}\n</zrodlo>"
        if feedback:
            user += ("\n\nPoprzednia odpowiedź miała błędy. Popraw je; cytaty kopiuj dosłownie z tekstu źródłowego, "
                     "a jeśli nie da się ich znaleźć, zostaw pole puste:\n- " + "\n- ".join(feedback))
        try:
            import anthropic
            errors: tuple = (anthropic.APIStatusError, anthropic.APIConnectionError)
        except ImportError:  # a test double client without the SDK installed
            errors = ()
        try:
            response = self.client.beta.messages.create(
                model=self.model,
                max_tokens=16000,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",  # on a policy decline the API re-runs the request on a fallback model
                system=SYSTEM_PROMPT,
                cache_control={"type": "ephemeral"},
                output_config={
                    "effort": self.effort,
                    "format": {"type": "json_schema", "schema": EXTRACTION_SCHEMA},
                },
                messages=[{"role": "user", "content": user}],
            )
        except errors as e:  # SDK already retried 429/5xx/connection errors twice
            raise LLMError(f"błąd API: {e}") from e
        if response.stop_reason == "refusal":
            raise LLMError("model odmówił odpowiedzi (refusal)")
        if response.stop_reason == "max_tokens":
            raise LLMError("odpowiedź ucięta (max_tokens)")
        self.model = getattr(response, "model", self.model)
        text = next((b.text for b in response.content if b.type == "text"), None)
        if text is None:
            raise LLMError("brak tekstu w odpowiedzi")
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise LLMError(f"niepoprawny JSON: {e}") from e


# --- offline rules ---------------------------------------------------------
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-ZŁŚŻŹĆŃÓĘĄ0-9„\"])")

USER_PATTERNS: list[tuple[str, str, str]] = [
    # (recipient_type, folded regex, label used as "who")
    ("gmina_miasto", r"\bgmin|\bmiast[aoy]\b|samorzad|\bjst\b|urzad[a-z]* miast", "gminy i miasta"),
    ("powiat_wojewodztwo", r"\bpowiaty\b|\bstarostw|samorzad[a-z]* (?:powiatow|wojewodz)|marszalk", "powiaty i województwa"),
    ("szkola", r"\bszkol|uczni|nauczyciel|przedszkol|edukacj", "szkoły i placówki oświatowe"),
    ("uczelnia", r"uczelni|uniwersytet|student|akademick", "uczelnie"),
    ("instytut_badawczy", r"instytut|laboratori|osrodk[a-z]* badawcz|naukowc", "instytuty i laboratoria badawcze"),
    ("ochrona_zdrowia", r"szpital|pacjent|lekarz|medycyn|klinik|ochron[a-z]* zdrowia|chirurg", "ochrona zdrowia"),
    ("administracja_sluzby", r"policj|straz|sluzb|administracj|kryminalist|wojsk|obronn", "administracja i służby"),
    ("przemysl", r"przemysl|produkcj|zaklad[a-z]* produkc|fabryk|wydobyw|hut|roboty", "przemysł"),
    ("msp", r"\bmsp\b|mal[a-z]* i srednich|przedsiebiorc|\bfirm", "firmy (MŚP)"),
    ("energetyka_media", r"energetyk|elektroenerget|sieci (?:elektro|ciepl|gaz|wod)|ciepłownic|wodociag", "energetyka i media"),
    ("transport", r"transport|lotnicz|\bkolej(?!n)|motoryzac|samochod|\bflot", "transport i lotnictwo"),
    ("msp", r"branz[a-z]* budowlan|instalacyjn|wykonawc[a-z]* budowl", "firmy budowlane i instalacyjne"),
    ("gmina_miasto", r"budynk[a-z]* (?:[a-z]+, )*publiczn|obiekt[a-z]* publiczn|zarzadc[a-z]* budynk", "zarządcy budynków publicznych"),
    ("rolnictwo", r"rolnik|rolnict|hodowc|uprawa|zywnosc", "rolnictwo i żywność"),
    ("ngo", r"organizacj[a-z]* pozarzad|fundacj|stowarzysz", "organizacje pozarządowe"),
    ("mieszkancy", r"mieszkanc|seniorz|seniorow|obywatel|rodzin|dzieci", "mieszkańcy"),
]
SIGNAL_PATTERNS: list[tuple[str, str]] = [
    ("zgloszenie_patentowe", r"zgloszen[a-z]* patentow|zgloszono do ochrony|wniosek patentow"),
    ("patent", r"\bpatent(?!ow[a-z]* zgloszen)|udzielon[a-z]* patent|ochron[a-z]* patentow"),
    ("demonstrator", r"demonstrator"),
    ("prototyp", r"prototyp"),
    ("pilotaz", r"pilotaz|pilotazow|program[a-z]* pilotaz"),
    ("testy_w_warunkach_rzeczywistych", r"warunkach rzeczywist|testy terenow|w warunkach przemyslow|testow[a-z]* u klient"),
    ("badania_laboratoryjne", r"warunkach laboratoryjn|badania laboratoryjn|skali laboratoryjn"),
    ("wdrozenie_u_beneficjenta", r"wdrozon[a-z]* w (?:naszej|firmie|spolce|zakladzie)|wdrozyli[a-z]*|wdrozenie wynik|wdrozenia wynik"
                                 r"|opracowani[a-z]* i wdrozeni|wdrozeni[a-z]* (?:nowatorsk|programu|modelu|metody)|\b(?:czterech|trzech|dwoch|kilku|\d+) edycj"),
    ("wdrozenie_poza_instytucja", r"wdrozon[a-z]* (?:u|w) (?:klient|partner|inn)|korzysta juz|stosowan[a-z]* (?:jest|sa) w"),
    ("produkt_na_rynku", r"na rynk[a-z]* (?:trafil|wprowadz)|wprowadzon[a-z]* na rynek|w sprzedazy|sprzedaz[a-z]* produkt|komercyjn[a-z]* dostep"),
    ("licencja", r"licencj"),
    ("spin_off", r"spin[- ]?off|spolk[a-z]* celow"),
]
SECTOR_PATTERNS: list[tuple[str, str]] = [
    ("lotnictwo", r"lotnic|samolot|dron|bezzalog|awiac|silnik[a-z]* lotnicz"),
    ("kosmos", r"kosmicz|satelit|kosmos"),
    ("motoryzacja", r"motoryzac|samochod|pojazd"),
    ("ICT", r"oprogramowan|informatycz|sztuczn[a-z]* inteligenc|uczeni[a-z]* maszynow|algorytm|aplikacj[a-z]* (?:mobiln|internetow|webow)"
            r"|platform[a-z]* (?:internet|cyfrow|onlin)|cyberbezpiecz|chmur[a-z]* obliczen|\bbig data\b|internet rzeczy|\biot\b"),
    ("zdrowie", r"medycyn|pacjent|szpital|terapi|leczeni|chorob|diagnost"),
    ("jakosc_zycia", r"jakos[a-z]* zycia|senior|niepelnospraw|zdrow[a-z]* styl|dobrostan"),
    ("energia", r"energi|wodor|fotowolt|elektroenerget|bateri|magazyn[a-z]* energii"),
    ("srodowisko", r"srodowisk|emisj|klimat|odpad|recykling|zanieczyszcz|powietrz"),
    ("edukacja", r"edukac|szkol|uczni|nauczyciel|dydaktyk|kompetencj"),
    ("administracja", r"administracj[a-z]* publiczn|urzad[a-z]* (?:gminy|miasta|marszalk|skarbow)|samorzad|policj|kryminalist"),
    ("przemysl", r"przemysl|produkcj|maszyn|robot|automatyzac"),
    ("budownictwo", r"budownic|budynk|konstrukcj|beton"),
    ("rolnictwo_zywnosc", r"rolnic|zywnos|lody|uprawa|hodowl|spozywcz"),
    ("transport", r"transport|\bkolej(?!n)|logistyk"),
]
PROBLEM_RE = (r"problem|\bbrak|trudnos|potrzeb|wyzwan|zapotrzebow|niedobor|zagroz|ryzyk|niewystarczaj|ogranicz"
              r"|zjawisk|deficyt|bariera|nieefektywn")
NOVELTY_RE =r"innowacyjn|nowatorsk|pierwsz[a-z]* w polsce|pierwsz[a-z]* na swiecie|nowej generacji|po raz pierwszy|unikaln|w przeciwienstwie|dotychczas"
# deployment requirements only; "wymagało" in the challenges section is about the project, not the user
REQUIREMENT_RE = (r"wdrozeni[a-z]* wymaga|do wdrozenia (?:potrzeb|niezbedn)|wymaga (?:jedynie|tylko|instalacji|montazu|zakupu|przeszkolenia|dostosowania)"
                  r"|koszt[a-z]* (?:wdrozenia|instalacji|zakupu|montazu)|nie wymaga")
EDU_RE = r"edukac|dydakty|pedagog|nauczyc|szkol|kurs|mooc|kompetencj"
SOCIAL_RE = r"spoleczn|integracj|wykluczen|senior|niepelnospraw"
PROCESS_RE = r"metod[a-z]* (?:produkcj|wytwarz)|technologi[a-z]* (?:produkcj|wytwarz)|proces"


def _sentences(text: str | None) -> list[str]:
    if not text:
        return []
    out: list[str] = []
    for para in text.split("\n"):
        out += [s.strip() for s in _SENT_SPLIT.split(para) if len(s.strip()) >= 12]
    return out


def _first(sentences: list[str], pattern: str) -> str | None:
    rx = re.compile(pattern)
    return next((s for s in sentences if rx.search(fold(s))), None)


def _trim(text: str, n: int = 300) -> str:
    return text if len(text) <= n else text[: n].rsplit(" ", 1)[0]


class RulesExtractor:
    """Keyword and section rules over NCBR-style narrative. Deliberately conservative."""

    name = "offline_rules"
    model = None

    def extract(self, source_text: str, record: dict, feedback: list[str] | None = None) -> dict:
        t = record.get("text") or {}
        problem_s = _sentences(t.get("problem"))
        result_s = _sentences(t.get("result")) + _sentences(t.get("market_readiness"))
        users_s = _sentences(t.get("users"))
        all_s = problem_s + result_s + users_s + _sentences(t.get("commercialization")) + _sentences(t.get("challenges"))
        title = record.get("title") or ""

        problem = (_first(problem_s, PROBLEM_RE) or (problem_s[0] if problem_s else "")
                   or (result_s[0] if result_s else ""))
        novelty = _first(problem_s + result_s, NOVELTY_RE) or ""
        requirement = _first(problem_s + result_s + users_s + _sentences(t.get("commercialization")), REQUIREMENT_RE) or ""

        users: list[dict] = []
        for rtype, pattern, label in USER_PATTERNS:
            if any(u["recipient_type"] == rtype for u in users):
                continue
            s = _first(users_s, pattern)
            if s:
                users.append({"who": label, "recipient_type": rtype, "quote": _trim(s)})

        signals: list[dict] = []
        for signal, pattern in SIGNAL_PATTERNS:
            s = _first(all_s, pattern)
            if s:
                signals.append({"signal": signal, "quote": _trim(s)})

        hay = fold(" ".join([title, source_text]))
        sectors = [sec for sec, pattern in SECTOR_PATTERNS if re.search(pattern, hay)][:4]

        contest = fold((record.get("funding") or {}).get("contest") or "")
        kw = fold(" ".join(record.get("keywords") or []))
        if re.search(EDU_RE, kw + " " + contest + " " + fold(title)) or "trzecia misja" in contest or "zintegrowane programy" in contest:
            itype = "edukacyjna"
        elif re.search(SOCIAL_RE, kw + " " + fold(title)):
            itype = "społeczna"
        elif re.search(PROCESS_RE, fold(title)):
            itype = "procesowa"
        else:
            itype = "technologiczna"
        itype_quote = (record.get("funding") or {}).get("contest") or ""
        if itype == "edukacyjna" and record.get("keywords"):
            itype_quote = record["keywords"][0]

        is_innovation = "tak" if (novelty or signals) and problem else ("niejasne" if problem else "nie")
        summary = " ".join(_sentences(record.get("intro")) [:1] or problem_s[:2]) or title
        return {
            "is_innovation": is_innovation,
            "is_innovation_quote": _trim(novelty or problem),
            "solution_name": {"value": title, "quote": title},
            "problem_solved": {"value": _trim(problem), "quote": _trim(problem)},
            "what_is_new": {"value": _trim(novelty), "quote": _trim(novelty)},
            "requirements": {"value": _trim(requirement), "quote": _trim(requirement)},
            "innovation_type": itype,
            "innovation_type_quote": itype_quote,
            "target_users": users,
            "maturity_signals": signals,
            "sectors": sectors,
            "summary_pl": _trim(summary, 500),
        }


# --- selection ---------------------------------------------------------------
def _claude_available() -> bool:
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
                or os.environ.get("ANTHROPIC_PROFILE"))


def get_providers(mode: str | None = None) -> list[Extractor]:
    """Ordered provider chain; the offline rules are always last."""
    mode = (mode or os.environ.get("RADAR_LLM") or "auto").lower()
    chain: list[Extractor] = []
    if mode == "claude" or (mode == "auto" and _claude_available()):
        try:
            chain.append(ClaudeExtractor())
        except LLMError:
            if mode == "claude":
                raise
    chain.append(RulesExtractor())
    return chain
