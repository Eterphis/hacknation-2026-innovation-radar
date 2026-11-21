"""Tool-calling loop of the implementation agent (T027), the "what speaks against" reviewer, and citation checks.

Protocol (plain JSON, so it works on every provider, including a 1.5B model behind llama.cpp without native
tool calling): each turn the model answers ONE object

    {"action": "tool", "name": "<tool>", "args": {...}}          -> code runs the tool, appends the observation
    {"action": "final", "summary": ..., "paths": [...], "risks": [...]}

Every observation gets an id (T1, T2, ...); every record a tool returns can be cited as "rec:<id>"; the card and
the Basal labels are "karta" and "basal". Each path, risk, objection and the summary must carry `cite: [...]`
with ids the agent actually saw, and any "#123" / "rec:123" in the text must be one of them. `check_citations`
enforces this in code: uncited or invented claims are sent back once, then dropped, and if nothing valid is left
the rule-based assessment stays.

Policies: `LLMPolicy` asks the router (local -> cloud; never the offline mock); `RulePolicy` is deterministic and
runs the same tools and the same checks, so the trace and the output shape are identical without any model.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy import select

from radar.basal import graph
from radar.basal.embed import fold
from radar.models import Card, Record

MAX_STEPS = 6
# Transcript budget sent each turn (chars): a 1.5B model on CPU in a 4k-token context needs it short.
CONTEXT_CHARS = int(__import__("os").environ.get("RADAR_AGENT_CONTEXT_CHARS", "5000"))
TOOLS = {
    "find_similar": "podobne pomysły z grafu (args: {\"k\": 1..8})",
    "regional_context": "ile pomysłów w tym sektorze ma każde województwo, gdzie są luki (args: {})",
    "recipients": "typy odbiorców i konkretne instytucje z danych, które mogą to wdrożyć (args: {})",
    "lookup_registry": "co wiemy o instytucji z danych: typ, województwo, liczba rekordów (args: {\"name\": \"...\"})",
}
REC_REF = re.compile(r"(?:rec:|#)(\d+)")
LEVELS_PL = ("niskie", "średnie", "wysokie")


# =========================================================================== tools (code, no LLM)
def _top(values) -> str | None:
    c = Counter(v for v in values if v).most_common(1)
    return c[0][0] if c else None


def lookup_registry(s, name: str, limit: int = 200) -> dict:
    """Internal registry from our own records until the RAD-on / KRS resolver exists (T023)."""
    key = " ".join(fold((name or "").split(",")[0]).split()[:3])
    if len(key) < 4:
        return {"name": name, "found": 0, "note": "za krótka nazwa"}
    hits = [r for r in s.scalars(select(Record).where(Record.status.in_(graph.INDEXED)).limit(limit * 20))
            if any(key in fold(a) for a in r.affiliations or [])][:limit]
    return {"name": name, "found": len(hits), "source": "rekordy radaru (rejestr RAD-on/KRS: T023)",
            "institution_type": _top(r.institution_type for r in hits), "voivodeship": _top(r.voivodeship for r in hits),
            "sectors": [k for k, _ in Counter(r.sector for r in hits if r.sector).most_common(3)],
            "records": [h.id for h in hits[:5]]}


@dataclass
class Toolbox:
    s: object
    rec: Record
    card: Card
    facts: dict[str, dict] = field(default_factory=dict)  # T1 -> {"tool", "args", "result"}
    rec_ids: set[int] = field(default_factory=set)
    cache: dict[str, object] = field(default_factory=dict)

    def run(self, name: str, args: dict | None) -> tuple[str, object]:
        from radar.pipeline import assess as A  # tools live next to the rules that use them

        args = args if isinstance(args, dict) else {}
        if name == "find_similar":
            k = max(1, min(8, int(args.get("k") or 5))) if str(args.get("k", 5)).isdigit() else 5
            res = graph.similar(self.s, self.rec, k=k)
            self.cache["similar"] = res
        elif name == "regional_context":
            res = A.tool_regional_context(self.s, self.rec)
            self.cache["ctx"] = res
        elif name == "recipients":
            res = A.tool_recipients(self.s, self.rec, self.cache.get("similar") or [])
            self.cache["recipients"] = res
        elif name == "lookup_registry":
            res = lookup_registry(self.s, str(args.get("name") or ((self.rec.affiliations or [""])[0])))
            self.cache.setdefault("registry", []).append(res)
        else:
            res = {"error": f"nieznane narzędzie {name!r}; dostępne: {sorted(TOOLS)}"}
        fid = f"T{len(self.facts) + 1}"
        self.facts[fid] = {"tool": name, "args": args, "result": res}
        self._collect_ids(res)
        return fid, res

    def _collect_ids(self, x) -> None:
        if isinstance(x, dict):
            for k, v in x.items():
                if k in ("record_id", "records") and v is not None:
                    for i in (v if isinstance(v, list) else [v]):
                        if isinstance(i, int):
                            self.rec_ids.add(i)
                else:
                    self._collect_ids(v)
        elif isinstance(x, list):
            for v in x:
                self._collect_ids(v)

    def valid_ids(self) -> set[str]:
        return {"karta", "basal", *self.facts, *(f"rec:{i}" for i in self.rec_ids), f"rec:{self.rec.id}"}


# =========================================================================== citation checks
def _cites(item: dict) -> list[str]:
    c = item.get("cite") or item.get("cites") or []
    return [str(x).strip() for x in (c if isinstance(c, list) else [c]) if str(x).strip()]


def check_citations(items: list[dict], valid: set[str], text_keys: tuple[str, ...], what: str) -> tuple[list[dict], list[str]]:
    """Keep items whose every citation is known and whose text names only known records. Returns (kept, errors)."""
    kept, errors = [], []
    known_recs = {v.split(":", 1)[1] for v in valid if v.startswith("rec:")}
    for i, it in enumerate(items or []):
        if not isinstance(it, dict):
            errors.append(f"{what}[{i}]: to nie jest obiekt")
            continue
        cites = _cites(it)
        label = str(it.get(text_keys[0]) or "")[:60]
        if not cites:
            errors.append(f"{what}[{i}] „{label}”: brak cytatu/odnośnika (cite)")
            continue
        bad = [c for c in cites if c not in valid]
        if bad:
            errors.append(f"{what}[{i}] „{label}”: odnośniki spoza faktów {bad}")
            continue
        text = " ".join(str(it.get(k) or "") for k in text_keys) + json.dumps(it.get("steps") or [], ensure_ascii=False)
        ghost = [m for m in REC_REF.findall(text) if m not in known_recs]
        if ghost:
            errors.append(f"{what}[{i}] „{label}”: tekst wskazuje rekordy, których narzędzia nie zwróciły {ghost}")
            continue
        it["cite"] = cites
        kept.append(it)
    return kept, errors


def validate_final(out: dict, box: Toolbox) -> tuple[dict, list[str]]:
    valid = box.valid_ids()
    paths, e1 = check_citations(out.get("paths") if isinstance(out.get("paths"), list) else [], valid, ("path", "why"), "paths")
    for p in paths:
        p["steps"] = [st for st in (p.get("steps") or []) if isinstance(st, dict) and st.get("step")]
        if not p["steps"]:
            e1.append(f"ścieżka „{p.get('path')}” bez kroków")
    paths = [p for p in paths if p["steps"]]
    risks, e2 = check_citations(out.get("risks") if isinstance(out.get("risks"), list) else [], valid,
                                ("risk", "mitigation"), "risks")
    for r in risks:
        if not r.get("mitigation"):
            e2.append(f"ryzyko „{r.get('risk')}” bez mitygacji")
        if r.get("level") not in LEVELS_PL:
            r["level"] = "średnie"
    risks = [r for r in risks if r.get("mitigation")]
    summary = out.get("summary") if isinstance(out.get("summary"), str) else None
    errs = e1 + e2
    if summary:
        s_ok, s_err = check_citations([{"summary": summary, "cite": out.get("summary_cite") or out.get("cite")}], valid,
                                      ("summary",), "summary")
        errs += s_err
        summary = summary if s_ok else None
    if not paths:
        errs.append("brak poprawnych ścieżek wdrożenia")
    return {"paths": paths, "risks": risks, "summary": summary}, errs


# =========================================================================== policies
AGENT_SYSTEM = """Jesteś agentem wdrożeniowym Podkarpackiego Centrum Innowacji. Oceniasz, czy pomysł da się wdrożyć,
jak, kto co robi i z jakim ryzykiem. Fakty zdobywasz WYŁĄCZNIE narzędziami:
{tools}
Każda odpowiedź to JEDEN obiekt JSON:
{{"action":"tool","name":"<narzędzie>","args":{{...}}}}
albo, gdy masz dość faktów (najpóźniej w kroku {max_steps}):
{{"action":"final","summary":"2 zdania","summary_cite":["T1"],
 "paths":[{{"path":"rozwój|komercjalizacja|wdrożenie w innej organizacji (transfer)|pilotaż|skalowanie i finansowanie",
   "why":"...","cite":["karta","T2"],"steps":[{{"step":"...","who":"...","time":"..."}}]}}],
 "risks":[{{"risk":"...","level":"niskie|średnie|wysokie","mitigation":"...","owner":"...","cite":["T1","rec:12"]}}]}}
Zasady: "cite" to identyfikatory faktów (T1, T2...), rekordów zwróconych przez narzędzia (rec:<id>), "karta" albo
"basal". Nie podawaj faktów, liczb ani instytucji, których nie ma w faktach. Po polsku."""

REVIEW_SYSTEM = """Jesteś recenzentem „co przemawia przeciw”. Dostajesz FAKTY i OCENĘ pomysłu. Wypisz 2-4 najmocniejsze
argumenty przeciw wdrożeniu (dublowanie istniejących rozwiązań, brak dowodów, koszt, bariery prawne, brak odbiorców).
Każdy argument musi wskazywać fakty. Odpowiedz WYŁĄCZNIE JSON:
{"against":[{"point":"...","severity":"niskie|średnie|wysokie","cite":["T1","rec:12"]}]}"""


def _observation(fid: str, res) -> str:
    return f"{fid} = " + json.dumps(res, ensure_ascii=False, default=str)[:900]


class LLMPolicy:
    name = "llm"

    def __init__(self, db=None):
        from radar.llm.router import router

        self.r, self.db, self.prov = router(), db, {}

    def ask(self, system: str, user: str, purpose: str) -> dict:
        out, prov = self.r.complete_json(system, user, purpose=purpose, exclude=("mock",), db=self.db)
        self.prov = prov
        return out


class RulePolicy:
    """Deterministic agent: same tools, same citation checks, no model."""

    name = "rules"
    PLAN = (("find_similar", {"k": 5}), ("regional_context", {}), ("recipients", {}))


def _rules_final(box: Toolbox, baseline: dict) -> dict:
    ids = {f["tool"]: fid for fid, f in box.facts.items()}
    sim_ids = [f"rec:{x['record_id']}" for x in box.cache.get("similar") or []][:3]
    paths = [dict(p, cite=["karta", "basal"]) for p in baseline["paths"]]
    risks = []
    for r in baseline["risks"]:
        cite = ["basal", "karta"]
        if "podobne" in r["risk"]:
            cite = [ids.get("find_similar", "basal"), *sim_ids]
        risks.append(dict(r, cite=cite))
    return {"paths": paths, "risks": risks, "summary": None}


def run_agent(s, rec: Record, card: Card, baseline_fn, use_llm: bool) -> dict:
    """Returns {"final", "trace", "facts", "by", "errors", "provenance", "toolbox"}.
    baseline_fn(box) -> rule-based {"paths","risks"} built from the tool results (also the fallback)."""
    box = Toolbox(s, rec, card)
    trace: list[dict] = []
    errors: list[str] = []
    if not use_llm:
        for name, args in RulePolicy.PLAN:
            fid, _ = box.run(name, args)
            trace.append({"step": len(trace) + 1, "tool": name, "args": args, "fact": fid, "by": "reguły"})
        if rec.affiliations:
            fid, _ = box.run("lookup_registry", {"name": rec.affiliations[0]})
            trace.append({"step": len(trace) + 1, "tool": "lookup_registry", "args": {"name": rec.affiliations[0]}, "fact": fid, "by": "reguły"})
        final, errs = validate_final(_rules_final(box, baseline_fn(box)), box)
        return {"final": final, "trace": trace, "facts": box.facts, "by": "reguły", "errors": errs, "provenance": {}, "toolbox": box}

    from radar.llm.router import AllProvidersFailed

    pol = LLMPolicy(db=s)
    task = json.dumps({"karta": {"nazwa": card.solution_name, "problem": card.problem_solved, "co_nowego": card.what_is_new,
                                 "dojrzalosc": card.maturity, "instytucje": (rec.affiliations or [])[:3]},
                       "basal": {k: (rec.basal or {}).get(k, {}).get("value") for k in
                                 ("sector", "tech_area", "innovation_type", "institution_type", "cost_level", "voivodeship")}},
                      ensure_ascii=False)
    system = AGENT_SYSTEM.format(tools="\n".join(f"- {k}: {v}" for k, v in TOOLS.items()), max_steps=MAX_STEPS)
    transcript = [f"ZADANIE (karta={rec.id}):\n{task}"]
    final = None
    repaired = False
    strikes = 0
    try:
        for step in range(1, MAX_STEPS + 3):
            if step > MAX_STEPS:
                transcript.append("Limit kroków: odpowiedz teraz action=final.")
            try:
                out = pol.ask(system, "\n\n".join(transcript)[-CONTEXT_CHARS:], "agent")
            except AllProvidersFailed as e:
                strikes += 1
                if not e.only_bad_output or strikes > 2:
                    raise
                trace.append({"step": step, "error": "odpowiedź nie jest obiektem JSON", "by": "local/cloud"})
                transcript.append(f"KROK {step}: odpowiedź nie była poprawnym JSON. Odpowiedz JEDNYM obiektem JSON.")
                continue
            act = out.get("action") or ("final" if "paths" in out else None)
            if act == "tool" and step <= MAX_STEPS:
                name, args = str(out.get("name") or ""), out.get("args") or {}
                fid, res = box.run(name, args)
                trace.append({"step": step, "tool": name, "args": args, "fact": fid, "by": pol.prov.get("provider"),
                              "latency_ms": pol.prov.get("latency_ms")})
                transcript.append(f"KROK {step}: {json.dumps(out, ensure_ascii=False)}\nOBSERWACJA {_observation(fid, res)}")
                continue
            if act != "final":
                transcript.append(f"KROK {step}: niepoprawna odpowiedź (brak action). Odpowiedz action=tool albo action=final.")
                continue
            cand, errs = validate_final(out, box)
            trace.append({"step": step, "final": True, "by": pol.prov.get("provider"), "errors": errs[:6]})
            if errs and not repaired:
                repaired = True
                transcript.append("ODPOWIEDŹ ODRZUCONA PRZEZ WALIDACJĘ CYTATÓW, popraw:\n- " + "\n- ".join(errs[:8]))
                continue
            errors = errs
            final = cand if cand["paths"] else None
            break
    except AllProvidersFailed as e:
        errors.append(f"LLM niedostępny: {e}")
    if final is None:  # rules on the facts gathered so far (missing tools are run now)
        for name, args in RulePolicy.PLAN:
            if name not in {f["tool"] for f in box.facts.values()}:
                fid, _ = box.run(name, args)
                trace.append({"step": len(trace) + 1, "tool": name, "args": args, "fact": fid, "by": "reguły (fallback)"})
        final, errs = validate_final(_rules_final(box, baseline_fn(box)), box)
        return {"final": final, "trace": trace, "facts": box.facts, "by": "reguły (fallback po LLM)",
                "errors": errors + errs, "provenance": pol.prov, "toolbox": box}
    by = f"agent LLM {pol.prov.get('provider')}/{pol.prov.get('model')}, {len([t for t in trace if t.get('tool')])} wywołań narzędzi"
    return {"final": final, "trace": trace, "facts": box.facts, "by": by, "errors": errors, "provenance": pol.prov, "toolbox": box}


# =========================================================================== reviewer: what speaks against
def rule_review(rec: Record, card: Card, box: Toolbox, scores: dict, risks: list[dict]) -> list[dict]:
    ids = {f["tool"]: fid for fid, f in box.facts.items()}
    out = []
    close = [x for x in box.cache.get("similar") or [] if x.get("closeness", 0) >= 0.1]
    if close:
        top = close[0]
        out.append({"point": f"istnieje bardzo podobne rozwiązanie (rec:{top['record_id']}, podobieństwo {top['similarity']:.2f}) — "
                             "wdrożenie może dublować cudzą pracę", "severity": "wysokie" if top.get("closeness", 0) >= 0.5 else "średnie",
                    "cite": [ids.get("find_similar", "basal"), f"rec:{top['record_id']}"]})
    if (scores.get("sila_dowodow") or {}).get("score", 5) <= 2:
        out.append({"point": "słabe dowody działania: mało cytatów ze źródła, brak DOI, patentu i kwot", "severity": "średnie", "cite": ["karta"]})
    if (card.maturity or "exploring") == "exploring":
        out.append({"point": "brak dowodu działania poza laboratorium lub instytucją twórcy", "severity": "wysokie", "cite": ["karta"]})
    if rec.cost_level in ("wysoki", "bardzo_wysoki"):
        out.append({"point": "koszt wdrożenia wysoki dla typowego odbiorcy publicznego", "severity": "średnie", "cite": ["basal"]})
    rcp = box.cache.get("recipients") or []
    if not [r for r in rcp if r.get("kind") == "instytucja z danych"]:
        out.append({"point": "w danych nie ma konkretnej instytucji, która potwierdziła potrzebę", "severity": "średnie",
                    "cite": [ids.get("recipients", "basal")]})
    if not out and risks:
        r = max(risks, key=lambda x: LEVELS_PL.index(x.get("level", "średnie")) if x.get("level") in LEVELS_PL else 1)
        out.append({"point": r["risk"], "severity": r.get("level", "średnie"), "cite": r.get("cite") or ["basal"]})
    return out[:4]


def llm_review(box: Toolbox, assessment: dict, db=None) -> tuple[list[dict] | None, dict, list[str]]:
    from radar.llm.router import AllProvidersFailed

    pol = LLMPolicy(db=db)
    facts = {fid: f["result"] for fid, f in box.facts.items()}
    user = ("FAKTY:\n" + json.dumps(facts, ensure_ascii=False, default=str)[:4500] + "\n\nOCENA:\n"
            + json.dumps({k: assessment.get(k) for k in ("paths", "risks", "summary", "total")}, ensure_ascii=False, default=str)[:2500])
    try:
        out = pol.ask(REVIEW_SYSTEM, user, "review")
    except AllProvidersFailed as e:
        return None, {}, [f"recenzent LLM niedostępny: {e}"]
    items, errs = check_citations(out.get("against") if isinstance(out.get("against"), list) else [], box.valid_ids(),
                                  ("point",), "against")
    for it in items:
        if it.get("severity") not in LEVELS_PL:
            it["severity"] = "średnie"
    return (items or None), pol.prov, errs
