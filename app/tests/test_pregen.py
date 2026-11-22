from types import SimpleNamespace

from radar import pregen
from radar.business import PERSONAS


def rec(**kw):
    base = dict(id=1, title="Szkolna pracownia robotyki", abstract="Uczniowie budują roboty z 12 zestawów. Program działa od 2021.",
                source_id="demo-zgloszenia", affiliations=["SP nr 3 w Rzeszowie"], amounts={"budzet": 50_000},
                sector="P_edukacja", tech_area=None, innovation_type="edukacyjna", institution_type="szkola",
                voivodeship="podkarpackie", cost_level="niski")
    base.update(kw)
    return SimpleNamespace(**base)


def card(**kw):
    base = dict(id=7, solution_name="Robotyka w każdej szkole", problem_solved="Brak zajęć technicznych w małych szkołach",
                summary_pl="Tani program zajęć z robotyki.", maturity="business_ready", score=72.0, decision="pending",
                assessment={}, target_users=["szkoły podstawowe"], provenance={"provider": "mock"})
    base.update(kw)
    return SimpleNamespace(**base)


def test_pregenerate_is_complete_and_deterministic():
    r, c = rec(), card()
    a, b = pregen.pregenerate(r, c), pregen.pregenerate(r, c)
    assert a == b
    assert a["version"] == pregen.VERSION and a["llm_calls"] == 0 and a["slogan_by"] == "reguły"
    assert a["brief"]["solution"] == "Robotyka w każdej szkole" and a["brief"]["hook"]
    assert 0 < len(a["slogan"]) <= pregen.SLOGAN_MAX
    assert a["business"]["version"].startswith("business/") and a["business"]["deploy_cost_pln"] > 0
    assert set(a["audiences"]) == set(PERSONAS)
    assert "szkoly" in a["top_audiences"]  # an educational, cheap idea fits schools
    assert a["audiences"]["inwestorzy"]["fits"] is False  # not a technology: not for investors


def test_rule_slogan_fits_and_falls_back_to_name():
    assert pregen.rule_slogan(rec(), card()) == "Robotyka w każdej szkole — brak zajęć technicznych w małych szkołach"
    long = card(problem_solved="Bardzo długi opis problemu " * 10)
    s = pregen.rule_slogan(rec(), long)
    assert s == "Robotyka w każdej szkole" and len(s) <= pregen.SLOGAN_MAX
    assert len(pregen.rule_slogan(rec(title="x " * 200), card(solution_name=None, problem_solved=None))) <= pregen.SLOGAN_MAX


def test_llm_slogan_is_opt_in_and_validated():
    r, c = rec(), card()
    good = lambda s, u: {"haslo": "Roboty z 12 zestawów dla małych szkół"}  # noqa: E731 - 12 is in the source
    invented = lambda s, u: {"haslo": "Roboty dla 500 szkół w Polsce"}  # noqa: E731 - 500 is not
    broken = lambda s, u: (_ for _ in ()).throw(TimeoutError())  # noqa: E731
    assert pregen.slogan(r, c, good) == ("Roboty z 12 zestawów dla małych szkół", "local-llm")
    assert pregen.slogan(r, c, invented)[1] == "reguły"
    assert pregen.slogan(r, c, broken)[1] == "reguły"
    assert pregen.slogan(r, c, lambda s, u: {"haslo": "x" * 200})[1] == "reguły"
    assert pregen.slogan(r, c, lambda s, u: {"haslo": "Robotyka " * 10})[1] == "reguły"  # 90 chars: cut by the cap
    assert pregen.slogan(r, c, lambda s, u: {"haslo": "**Robotyka dla małych szkół**"}) == ("Robotyka dla małych szkół", "local-llm")
    assert pregen.slogan(r, c, lambda s, u: {"haslo": "Program pomaga uczniom rozwijać kompetencje i pobudzać do"})[1] == "reguły"
    assert pregen.pregenerate(r, c, good)["llm_calls"] == 1


def test_rejected_and_infrastructure_fit_no_audience():
    assert not any(v["fits"] for v in pregen.audiences(rec(), card(decision="rejected"),
                                                         pregen.business_case(rec(), card())).values())
    road = rec(title="Budowa drogi ekspresowej S19", innovation_type="organizacyjna", sector="H_transport")
    assert pregen.pregenerate(road, card())["top_audiences"] == []


def test_refresh_only_when_inputs_change():
    r, c = rec(), card()
    stored = {c.id: pregen.pregenerate(r, c)}
    res, st = pregen.pregenerate_many([(r, c)], stored)
    assert res == {} and st["skipped"] == 1 and st["computed"] == 0
    c.likes = 99  # not an input
    assert not pregen.needs_refresh(stored[c.id], r, c)
    c.score = 90.0
    res, st = pregen.pregenerate_many([(r, c)], stored)
    assert st["computed"] == 1 and res[c.id]["audiences"]["szkoly"]["rank"] > stored[c.id]["audiences"]["szkoly"]["rank"]


def test_no_large_llm_share():
    pairs = [(rec(), card(id=i, provenance={"provider": p})) for i, p in enumerate(["mock", "local", None, "anthropic"])]
    _, st = pregen.pregenerate_many(pairs)
    assert st["no_large_llm"] == 3 and st["no_large_llm_pct"] == 75.0


def test_pregenerate_matches_api_on_demo_data():
    """On the demo snapshots: every card pregenerates, and audience fit agrees with /api/personas/{key}."""
    from fastapi.testclient import TestClient
    from sqlalchemy import select

    from radar.db import session
    from radar.models import Card, Record
    from radar.pipeline.tasks import harvest

    for src in ("demo-zgloszenia", "demo-kohesio", "demo-publikacje"):
        harvest.apply((src,)).get()
    with session() as s:
        pairs = [(r, r.card) for r in s.scalars(select(Record).join(Card, Card.record_id == Record.id)).all()]
        res, st = pregen.pregenerate_many(pairs)
        assert st["cards"] == st["computed"] == len(res) > 0
        assert st["no_large_llm_pct"] > 90
        fit = {k: {cid for cid, v in res.items() if v["audiences"][k]["fits"]} for k in PERSONAS}
    from radar.api.main import app

    with TestClient(app) as c:
        for key in PERSONAS:
            items = c.get(f"/api/personas/{key}", params={"limit": 60}).json()["items"]
            assert {i["card_id"] for i in items} <= fit[key], key


# ------------------------------------------------------------------------------------------------ wiring (after #11)
def _demo():
    from radar.pipeline.tasks import harvest

    for src in ("demo-zgloszenia", "demo-kohesio", "demo-publikacje"):
        harvest.apply((src,)).get()


def test_import_pregenerates_and_api_only_reads(monkeypatch):
    """Scoring an imported batch stores pregen; persona, match, card and feed endpoints never compute it again."""
    from fastapi.testclient import TestClient
    from sqlalchemy import select

    from radar.db import session
    from radar.models import Card

    _demo()
    with session() as s:
        cards = s.scalars(select(Card).where(Card.score.is_not(None))).all()
        assert cards and all(c.pregen and c.pregen["version"] == pregen.VERSION for c in cards)

    import radar.business
    import radar.pregen as P

    def boom(*a, **k):
        raise AssertionError("API must read the stored business case, not compute it")

    monkeypatch.setattr(radar.business, "business_case", boom)
    monkeypatch.setattr(P, "business_case", boom)
    from radar.api.main import app

    with TestClient(app) as c:
        for key in PERSONAS:
            assert c.get(f"/api/personas/{key}").status_code == 200
        items = c.get("/api/match", params={"role": "samorzady"}).json()["items"]
        assert items
        card = c.get(f"/api/cards/{items[0]['card_id']}").json()
        assert card["business"]["version"].startswith("business/") and card["slogan"]
        assert all(i["slogan"] for i in c.get("/api/feed").json())


def test_cli_pregenerate_is_incremental(capsys):
    import json

    from radar.cli import main

    _demo()
    main(["pregenerate"])
    first = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert first["cards"] > 0 and first["computed"] == 0 and first["skipped"] == first["cards"]  # scored = stored
    main(["pregenerate", "--force"])
    forced = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert forced["computed"] == forced["cards"] and forced["no_large_llm_pct"] == 100.0


def test_nightly_beat_runs_pregenerate():
    from radar.pipeline.celery_app import beat_schedule

    e = beat_schedule()["pregenerate-nightly"]
    assert e["task"] == "radar.pipeline.tasks.pregenerate" and e["options"]["queue"] == "score"
