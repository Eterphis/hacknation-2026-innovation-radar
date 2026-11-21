from fastapi.testclient import TestClient

from radar.business import PERSONAS
from radar.pipeline.tasks import harvest


def test_personas_rank_ideas_with_business_cases():
    for src in ("demo-zgloszenia", "demo-kohesio", "demo-publikacje"):
        harvest.apply((src,)).get()
    from radar.api.main import app

    with TestClient(app) as c:
        assert {p["key"] for p in c.get("/api/personas").json()} == set(PERSONAS)
        for key in PERSONAS:
            r = c.get(f"/api/personas/{key}").json()
            assert r["name"] and r["promise"] and "summary" in r
            import math
            metrics = [(i["score"] or 0) * .75 + min(25, 25 * math.log10(1 + i["business"]["metric"]) / 8) for i in r["items"]]
            assert metrics == sorted(metrics, reverse=True)
        sam = c.get("/api/personas/samorzady").json()
        assert sam["items"], "municipalities must get ready-to-copy non-technological ideas"
        assert all(i["labels"]["innovation_type"]["value"] != "technologiczna" for i in sam["items"])
        card = c.get(f"/api/cards/{sam['items'][0]['card_id']}").json()
        b = card["business"]
        assert b["deploy_cost_pln"] > 0 and b["market"]["tam_pln"] >= b["market"]["som_3y_pln"] > 0
        assert 0 < b["valuation"]["success_probability"] < 1 and b["assumptions"] and b["funding"]
        assert c.get("/api/personas/nieznana").status_code == 404


def test_match_profile_is_explainable():
    harvest.apply(("demo-zgloszenia",)).get()
    from radar.api.main import app

    with TestClient(app) as c:
        r = c.get("/api/match", params={"role": "samorzady", "voivodeship": "podkarpackie", "sectors": "Q_zdrowie",
                                        "budget": "sredni", "stage": "tech_ready", "goal": "wdrozenie"}).json()
        assert r["items"] and r["profile"]["voivodeship"] == "podkarpackie"
        top = r["items"][0]
        assert 0 < top["match"] <= 100 and top["why"]
        assert [i["match"] for i in r["items"]] == sorted((i["match"] for i in r["items"]), reverse=True)


# ------------------------------------------------------------------ adopters from GUS BDL (adopters.json)
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from radar import business

GUS = {
    "schema": "radar.adopters/v1", "source": "GUS, Bank Danych Lokalnych", "fetched_at": "2026-11-22T08:00:00+00:00",
    "adopters": {
        "gminy": {"label": "gmin", "poland": 2477, "year": 2024, "variable_id": 60559, "variable_ids": [60559],
                  "source": "GUS BDL, temat P1413, zmienna 60559", "fetched_at": "2026-11-22T08:00:00+00:00",
                  "by_voivodeship": {"podkarpackie": 160, "mazowieckie": 314, "łódzkie": 177}},
    },
}


def rec(**kw):
    base = dict(title="System zgłaszania usterek dla mieszkańców", abstract="", sector="O_administracja",
                innovation_type="organizacyjna", institution_type="jst", cost_level="sredni", amounts={},
                voivodeship="podkarpackie")
    return SimpleNamespace(**{**base, **kw})


CARD = SimpleNamespace(maturity="business_ready")


@pytest.fixture
def gus_file(tmp_path, monkeypatch):
    p = tmp_path / "adopters.json"
    p.write_text(json.dumps(GUS, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(business, "ADOPTERS_FILE", p)
    business.load_adopters.cache_clear()
    yield p
    business.load_adopters.cache_clear()


def test_sam_is_the_regions_own_gus_count(gus_file):
    bc = business.business_case(rec(), CARD)
    a = bc["adopters"]
    assert a["count"] == 2477 and a["source"] == "GUS BDL" and a["year"] == 2024 and a["regional"] == 160
    assert a["variable_ids"] == [60559] and a["fetched_at"] == "2026-11-22"
    assert bc["market"]["sam_pln"] == 160 * bc["deploy_cost_pln"]  # not tam / 16
    assert bc["market"]["sam_pln"] != round(bc["market"]["tam_pln"] / 16)
    assert "GUS BDL, 2024" in a["who"]
    line = bc["assumptions"][0]
    assert "zmienne BDL 60559" in line and "pobrano 2026-11-22" in line and "podkarpackie: 160" in line
    assert "szacunek" not in line


def test_voivodeship_lookup_ignores_diacritics_and_case(gus_file):
    assert business.adopters_for("gminy", "Łódzkie")["regional"] == 177
    assert business.adopters_for("gminy", "lodzkie")["regional"] == 177


def test_whole_country_when_record_has_no_region(gus_file):
    bc = business.business_case(rec(voivodeship=None), CARD)
    assert bc["market"]["sam_pln"] == bc["market"]["tam_pln"]
    assert bc["adopters"]["regional"] is None


def test_key_missing_from_file_falls_back_to_labelled_estimate(gus_file):
    bc = business.business_case(rec(sector="Q_zdrowie"), CARD)  # hospitals are not in the fixture
    a = bc["adopters"]
    assert a["source"] == "szacunek" and a["count"] == business.ADOPTERS["szpitale"][0]
    assert bc["market"]["sam_pln"] == round(a["count"] / 16) * bc["deploy_cost_pln"]
    assert "(szacunek)" in bc["assumptions"][0] and "1/16 kraju" in bc["assumptions"][0]


def test_no_file_means_estimates(tmp_path, monkeypatch):
    monkeypatch.setattr(business, "ADOPTERS_FILE", tmp_path / "none.json")
    business.load_adopters.cache_clear()
    try:
        a = business.adopters_for("gminy", "podkarpackie")
        assert a["source"] == "szacunek" and a["count"] == business.ADOPTERS["gminy"][0]
    finally:
        business.load_adopters.cache_clear()


def test_every_adopter_key_has_an_estimate():
    keys = set(business.BY_SECTOR.values()) | set(business.BY_INNOVATION.values()) | {"msp_sektor"}
    assert keys <= set(business.ADOPTERS)


def test_shipped_gus_file_is_complete():
    """When app/radar/data/adopters.json is present it must carry source, date and variable ids for every number."""
    path = Path(business.__file__).parent / "data" / "adopters.json"
    if not path.exists():
        pytest.skip("adopters.json not generated yet (python -X utf8 scripts/fetch_gus_adopters.py)")
    doc = json.loads(path.read_text("utf-8"))
    assert doc["source"] and doc["fetched_at"]
    for key, g in doc["adopters"].items():
        assert key in business.ADOPTERS, key
        assert g["poland"] > 0 and g["year"] and g["source"] and g["fetched_at"] and g["variable_ids"], key
        assert len(g["by_voivodeship"]) == 16, key
        assert abs(sum(g["by_voivodeship"].values()) - g["poland"]) <= max(2, g["poland"] * .01), key
