from fastapi.testclient import TestClient
from sqlalchemy import func, select

from radar.basal.classifier import classify, mask_pii, voivodeship
from radar.basal.embed import HashingEmbedder
from radar.db import session
from radar.models import Card, Edge, Record
from radar.pipeline.tasks import harvest


def test_basal_axes_and_gate():
    b = classify(title="Gminna wypożyczalnia sprzętu rehabilitacyjnego",
                 abstract="Gmina uruchomiła wypożyczalnię prowadzoną przez ośrodek pomocy społecznej. Usługa działa od "
                          "2024 roku, wypożyczono 300 sztuk sprzętu dla seniorów i osób po wypisie ze szpitala.",
                 affiliations=["Gmina Sanok"], kind="solution", min_chars=80)
    assert b["decision"] == "accept"
    assert b["sector"]["value"] == "Q_zdrowie"
    assert b["institution_type"]["value"] == "jst"
    assert b["voivodeship"]["value"] == "podkarpackie"  # from the city
    assert b["maturity_hint"]["value"] == "business_ready"
    assert 0 < b["priority"] <= 1

    spam = classify(title="Oferta pracy", abstract="Rekrutacja na stanowisko, oferta pracy, umowa o pracę. " * 6,
                    affiliations=["Firma XYZ sp. z o.o."], kind="solution", min_chars=80)
    assert spam["decision"] == "reject"
    assert any("firma prywatna" in r for r in spam["reject_reasons"])


def test_pii_masking_and_region():
    text, found = mask_pii("Kontakt: jan.kowalski@example.org, tel. 600 100 200, PESEL 90010112345")
    assert set(found) == {"email", "telefon", "pesel"} and "@" not in text
    assert voivodeship("Politechnika Wrocławska").value == "dolnośląskie"


def test_hashing_embedder_similarity():
    e = HashingEmbedder()
    a, b, c = e.embed(["oczyszczanie ścieków w małych gminach", "oczyszczalnia ścieków dla małej gminy",
                       "program mentoringu dla uczniów"])
    assert a @ b > a @ c


def test_full_flow_ranking_graph_feed_and_likes():
    for src in ("demo-publikacje", "demo-kohesio", "demo-zgloszenia"):
        harvest.apply((src,)).get()
    with session() as s:
        rejected = s.scalars(select(Record).where(Record.status == "rejected")).all()
        assert any("Oferta pracy" in (r.title or "") for r in rejected)
        cards = s.scalars(select(Card).where(Card.score.is_not(None))).all()
        assert len(cards) >= 15
        c = cards[0]
        a = c.assessment
        assert a["paths"] and all(st.get("who") for p in a["paths"] for st in p["steps"])
        assert all(r.get("mitigation") and r.get("owner") for r in a["risks"])
        assert set(a["scores"]) == set(a["criteria"]) and 0 <= a["total"] <= 100
        assert a["metrics"] and c.brief["next_step"]
        assert s.scalar(select(func.count()).select_from(Edge)) > 0

    from radar.api.main import app

    api = TestClient(app)
    r = api.get("/api/ideas", params={"voivodeship": "podkarpackie", "sort": "score"}).json()
    assert r["total"] >= 5 and r["facets"]["sector"]
    scores = [i["score"] for i in r["items"]]
    assert scores == sorted(scores, reverse=True)
    g = api.get("/api/graph").json()
    assert any(n["type"] == "idea" for n in g["nodes"]) and any(l["kind"] == "sector" for l in g["links"])
    reg = api.get("/api/regions", params={"sector": "P_edukacja"}).json()
    assert len(reg["regions"]) == 16 and any(x["gap"] > 0 for x in reg["regions"])
    feed = api.get("/api/feed").json()
    assert feed and feed[0]["brief"]["hook"]
    cid = feed[0]["card_id"]
    assert api.post(f"/api/cards/{cid}/like", headers={"X-Voter": "browser-123456"}).json() == {"card_id": cid, "liked": True, "likes": 1}
    assert api.post(f"/api/cards/{cid}/like", headers={"X-Voter": "browser-123456"}).json()["likes"] == 0
    assert api.post(f"/api/cards/{cid}/like").status_code == 400
    live = api.post("/api/basal/classify", json={"title": "Aplikacja do zgłaszania usterek",
                                                 "description": "Urząd gminy uruchomił aplikację online do zgłaszania usterek przez mieszkańców ze zdjęciem i mapą.",
                                                 "institution_type": "JST"}).json()
    assert live["decision"] == "accept" and live["institution_type"]["value"] == "jst"


def test_basal_learns_from_operator_decisions():
    harvest.apply(("demo-zgloszenia",)).get()
    from radar.api.main import app

    api = TestClient(app)
    cards = api.get("/api/cards", params={"limit": 50}).json()
    assert api.post("/api/basal/train").json()["trained"] is False  # no decisions yet
    for i, c in enumerate(cards[:10]):
        api.post(f"/api/cards/{c['id']}/decision", json={"decision": "approved" if i % 2 else "rejected"})
    r = api.post("/api/basal/train").json()
    assert r["trained"] and r["n"] == 10
    b = api.post("/api/basal/classify", json={"title": "Program dla seniorów w gminie",
                                              "description": "Gmina uruchomiła program wsparcia seniorów prowadzony przez ośrodek pomocy społecznej, działa od roku."}).json()
    assert b["learned_accept"] is not None


def test_insights_answers_business_questions():
    for src in ("demo-kohesio", "demo-zgloszenia", "demo-publikacje"):
        harvest.apply((src,)).get()
    from radar.api.main import app

    r = TestClient(app).get("/api/insights").json()
    assert r["kpi"]["ideas"] >= 15 and r["trends"] and r["portfolio"]
    for k in ("standouts", "advanced", "realized", "budget", "cheap", "hidden", "duplicates", "gaps"):
        assert k in r and k in r["rules"]
    assert all(x["maturity_i"] >= 2 for x in r["realized"])
    assert all(x["cost_i"] >= 2 for x in r["budget"]) and all(x["cost_i"] <= 1 for x in r["cheap"])
