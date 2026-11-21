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
