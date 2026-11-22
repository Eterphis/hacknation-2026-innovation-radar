"""Issue #30 task 5: procurement dossier (pure rules + endpoint mounted on a test app)."""

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from radar import procurement as P


def _rec(**kw):
    base = dict(title="System zgłoszeń mieszkańców", sector="O_administracja", innovation_type="organizacyjna",
                affiliations=["Gmina Przykładowa"], voivodeship="podkarpackie", source_id="demo", url=None,
                cost_level="sredni", amounts={}, extra={})
    return SimpleNamespace(**{**base, **kw})


def _card(**kw):
    base = dict(id=7, solution_name="Zgłoś usterkę", problem_solved="Mieszkańcy nie mają jak zgłosić usterki.",
                what_is_new="Aplikacja z mapą i statusem zgłoszenia.", summary_pl=None, target_users=["mieszkańcy"],
                maturity="market_ready")
    return SimpleNamespace(**{**base, **kw})


BC = {"deploy_cost_pln": 180_000, "savings_per_adopter_pln": 360_000, "payback": "1–2 lata",
      "assumptions": ["odbiorcy: ...", "koszt wdrożenia u odbiorcy: 180 000 zł (środek przedziału)"],
      "funding": [{"programme": "FERS — innowacje społeczne", "for": "JST"}]}


def test_procedure_follows_2026_thresholds():
    assert P.procedure(169_999, "market_ready")["mode"].startswith("poza ustawą")
    assert P.procedure(170_000, "market_ready")["mode"] == "tryb podstawowy"
    assert P.procedure(930_959, "market_ready")["mode"] == "tryb podstawowy"
    assert P.procedure(930_960, "market_ready")["mode"] == "przetarg nieograniczony"
    assert P.EU_THRESHOLD_PLN == 930_960
    t = P.procedure(1, None)["thresholds"]
    assert t["source"] and t["as_of"] == "2026-01-01"


def test_innovative_routes_only_before_market():
    assert P.procedure(500_000, "tech_ready")["alternatives"]
    assert not P.procedure(500_000, "market_ready")["alternatives"]


def test_price_weight_never_above_60_and_weights_sum_to_100():
    for rec, card in [(_rec(), _card()), (_rec(innovation_type="technologiczna"), _card(maturity="tech_ready"))]:
        w = P.criteria(rec, card)["weights"]
        assert w["cena"] <= 60 and sum(w.values()) == 100


def test_dossier_uses_only_computed_fields():
    d = P.dossier(_rec(), _card(), BC, [{"name": "Firma X", "voivodeship": "mazowieckie", "ready": 2, "ideas": 3}])
    assert d["estimated_value"]["net_pln"] == 180_000 and d["procedure"]["mode"] == "tryb podstawowy"
    assert d["subject"]["need"].startswith("Mieszkańcy") and d["subject"]["cpv"]["code"] == "79400000-8"
    assert [o["role"] for o in d["implementers"]] == ["twórca", "dostawca w sektorze"]
    assert d["funding"] == ["FERS — innowacje społeczne"]
    page = P.render(d)
    assert "Teczka zamówienia publicznego" in page and "Kryteria oceny ofert" in page and "180 000 zł" in page


def test_endpoint_json_and_print():
    from radar.api.procurement import router
    from radar.investor import reset_cache
    from radar.pipeline.tasks import harvest

    for src in ("demo-zgloszenia", "demo-kohesio", "demo-publikacje"):
        harvest.apply((src,)).get()
    reset_cache()
    from radar.db import session
    from radar.models import Card
    from sqlalchemy import select

    with session() as s:
        cid = s.scalar(select(Card.id).where(Card.maturity.is_not(None)).limit(1))
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as c:
        d = c.get(f"/api/cards/{cid}/procurement").json()
        assert d["version"] == "procurement/v1" and d["estimated_value"]["net_pln"] > 0
        assert d["procedure"]["mode"] and d["implementers"]
        assert "Teczka zamówienia" in c.get(f"/api/cards/{cid}/procurement", params={"format": "html"}).text
        assert c.get("/api/cards/999999/procurement").status_code == 404
