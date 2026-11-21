"""Agent loop (T027): tool calls, citation checks, reviewer, fallback, LLM call metrics."""

import json

import pytest
from sqlalchemy import select

import radar.llm.router as R
from radar.db import session
from radar.llm.providers import PROVIDERS, Provider, ProviderError
from radar.models import Card, LlmCall, Record
from radar.pipeline import agent as AG
from radar.pipeline.assess import assess
from radar.pipeline.tasks import harvest


class Scripted(Provider):
    """Fake model: replays `script` (a list of dicts or callables taking the user prompt)."""

    name, model = "local", "scripted"
    script: list = []
    seen: list = []

    def complete_json(self, system, user):
        Scripted.seen.append((system[:40], user))
        if not Scripted.script:
            raise ProviderError("script exhausted")
        step = Scripted.script.pop(0)
        return step(user) if callable(step) else step


@pytest.fixture
def scripted(monkeypatch):
    monkeypatch.setitem(PROVIDERS, "local", Scripted)
    monkeypatch.setenv("RADAR_LLM_PROVIDERS", "local,mock")
    from radar.config import get_settings

    get_settings.cache_clear()
    R._router = None
    Scripted.script, Scripted.seen = [], []
    harvest.apply(("demo-zgloszenia",)).get()  # cards scored by the scripted model too: give it nothing -> rules
    R._router = None
    yield Scripted
    R._router = None


def _a_ready_card(s):
    rec = s.scalars(select(Record).where(Record.status == "ready")).first()
    return rec, rec.card


def _sim_id(user: str) -> str:
    """Take a real record id from the find_similar observation, like a model would."""
    obs = user.rsplit("OBSERWACJA T1 = ", 1)[-1].split("\n")[0]
    items = json.loads(obs)
    return f"rec:{items[0]['record_id']}" if items else "basal"


def test_rules_agent_runs_every_tool_and_cites():
    harvest.apply(("demo-zgloszenia",)).get()
    with session() as s:
        rec, card = _a_ready_card(s)
        a = assess(s, rec, card)
    tools = [t["tool"] for t in a["agent"]["trace"] if t.get("tool")]
    assert {"find_similar", "regional_context", "recipients"} <= set(tools)
    assert a["by"] == "reguły" and a["agent"]["citation_errors"] == []
    assert all(p["cite"] for p in a["paths"]) and all(r["cite"] for r in a["risks"])
    assert a["against"] and all(x["cite"] for x in a["against"]) and a["against_by"] == "reguły"


def test_llm_agent_loop_validates_citations(scripted):
    final = lambda user: {  # noqa: E731
        "action": "final", "summary": "Rozwiązanie działa w gminie i da się je przenieść.", "summary_cite": ["karta"],
        "paths": [{"path": "wdrożenie w innej organizacji (transfer)", "why": "działa u twórcy", "cite": ["karta", "T1"],
                   "steps": [{"step": "wizyta studyjna", "who": "PCI", "time": "1 mies."}]},
                  {"path": "skalowanie", "why": "zmyślone: wdrożone w #999999", "cite": ["T9"],
                   "steps": [{"step": "x", "who": "y", "time": "z"}]}],
        "risks": [{"risk": "dublowanie", "level": "średnie", "mitigation": "połączyć zespoły", "owner": "PCI",
                   "cite": ["T1", _sim_id(user)]},
                  {"risk": "bez źródła", "level": "wysokie", "mitigation": "?", "owner": "?"}]}
    scripted.script = [
        {"action": "tool", "name": "find_similar", "args": {"k": 3}},
        {"action": "tool", "name": "lookup_registry", "args": {"name": "Gmina Sanok"}},
        final,
        final,  # after the repair request the model repeats itself: invalid items are dropped, valid ones stay
        {"against": [{"point": "podobne rozwiązanie już istnieje", "severity": "wysokie", "cite": ["T1"]},
                     {"point": "zmyślony argument", "severity": "wysokie", "cite": ["rec:424242"]}]},
    ]
    with session() as s:
        rec, card = _a_ready_card(s)
        a = assess(s, rec, card)
    assert a["by"].startswith("agent LLM local/scripted")
    assert [p["path"] for p in a["paths"]] == ["wdrożenie w innej organizacji (transfer)"]
    assert [r["risk"] for r in a["risks"]] == ["dublowanie"]
    assert any("odnośniki spoza faktów" in e for e in a["agent"]["citation_errors"])
    assert any("brak cytatu" in e for e in a["agent"]["citation_errors"])
    assert [x["point"] for x in a["against"]] == ["podobne rozwiązanie już istnieje"] and a["against_by"].startswith("LLM local")
    # the repair message reached the model, and the tool observations were in its context
    assert any("ODRZUCONA PRZEZ WALIDACJĘ" in u for _, u in scripted.seen)
    assert any("OBSERWACJA T2" in u for _, u in scripted.seen)
    # tools the model skipped were filled in for the scores
    assert {"regional_context", "recipients"} <= {t["tool"] for t in a["agent"]["trace"] if t.get("tool")}
    with session() as s:
        calls = s.scalars(select(LlmCall).where(LlmCall.provider == "local")).all()
        assert {c.purpose for c in calls} >= {"agent", "review"} and all(c.latency_ms >= 0 for c in calls)


def test_llm_down_falls_back_to_rules(scripted):
    scripted.script = []  # every call raises ProviderError -> circuit opens, rules take over, mock is never the agent
    with session() as s:
        rec, card = _a_ready_card(s)
        a = assess(s, rec, card)
    assert a["by"] == "reguły (fallback po LLM)" and a["paths"] and a["against"]
    with session() as s:
        assert s.scalars(select(LlmCall).where(LlmCall.ok.is_(False))).first() is not None


def test_check_citations_rejects_ghost_records():
    kept, errs = AG.check_citations([{"risk": "x w rec:5", "mitigation": "m", "cite": ["T1"]},
                                     {"risk": "y", "mitigation": "m", "cite": ["T1", "rec:7"]}],
                                    {"T1", "rec:7", "karta"}, ("risk", "mitigation"), "risks")
    assert [k["risk"] for k in kept] == ["y"] and "rekordy, których narzędzia nie zwróciły" in errs[0]


def test_parse_json_takes_first_object_and_bad_output_keeps_circuit_closed(scripted):
    from radar.llm.providers import BadOutput, _parse_json

    assert _parse_json('Oto wynik: ```json\n{"action": "tool", "name": "recipients"}\n``` i {"x": 1}') == {"action": "tool", "name": "recipients"}
    with pytest.raises(BadOutput):
        _parse_json("nie wiem")

    def bad(_user):
        raise BadOutput("no JSON object in model output")

    scripted.script = [bad, {"action": "tool", "name": "find_similar", "args": {}},
                       {"action": "final", "paths": [{"path": "pilotaż", "why": "x", "cite": ["karta"],
                                                      "steps": [{"step": "pilotaż u odbiorcy", "who": "PCI", "time": "2 mies."}]}],
                        "risks": []}, {"against": []}]
    with session() as s:
        rec, card = _a_ready_card(s)
        a = assess(s, rec, card)
    assert a["by"].startswith("agent LLM") and [p["path"] for p in a["paths"]] == ["pilotaż"]
    assert any(t.get("error") for t in a["agent"]["trace"])
    assert a["risks"]  # the model gave none: the rule-based risks stay
    assert R.router().real_available()  # one malformed answer did not open the circuit
