"""Round 2: investor signals, memo, watchlists, deployments, partner API."""

from fastapi.testclient import TestClient

from radar.pipeline.tasks import harvest


def _client():
    for src in ("demo-zgloszenia", "demo-kohesio", "demo-publikacje"):
        harvest.apply((src,)).get()
    from radar.api.main import app
    from radar.investor import reset_cache

    reset_cache()
    return TestClient(app)


def _some_card(c) -> int:
    return c.get("/api/ideas", params={"maturity": "business_ready,market_ready", "limit": 1}).json()["items"][0]["card_id"]


def test_card_has_investor_signals_and_explained_adjustment():
    with _client() as c:
        d = c.get(f"/api/cards/{_some_card(c)}").json()
        inv = d["investor"]
        assert inv["ip"]["strength"] in ("none", "weak", "medium", "strong")
        assert 0 <= inv["readiness"]["score"] <= 100 and sum(inv["readiness"]["parts"].values()) >= inv["readiness"]["score"]
        adj = inv["adjusted"]
        assert adj["success_probability"] >= d["business"]["valuation"]["success_probability"]
        # every percentage point added is explained
        assert (adj["success_probability"] > d["business"]["valuation"]["success_probability"]) == bool(adj["reasons"])


def test_memo_renders_both_versions_without_llm():
    with _client() as c:
        cid = _some_card(c)
        inv = c.get(f"/api/cards/{cid}/memo").text
        wyk = c.get(f"/api/cards/{cid}/memo", params={"kind": "wykonawca"}).text
        assert "Memo inwestycyjne" in inv and "Gotowość inwestycyjna" in inv and "Ryzyka" in inv
        assert "Specyfikacja wdrożenia" in wyk and "Kto może wdrożyć" in wyk
        assert c.get("/api/cards/999999/memo").status_code == 404


def test_watchlist_feed_respects_threshold_and_needs_no_personal_data():
    with _client() as c:
        prof = {"role": "samorzady", "voivodeship": "", "sectors": [], "budget": "wysoki", "goal": "wdrozenie"}
        w = c.post("/api/watch", json={"profile": prof, "min_match": 50}).json()
        assert len(w["token"]) >= 20 and "@" not in w["feed_url"]
        items = c.get(f"/api/watch/{w['token']}").json()["items"]
        assert items and all(i["match"] >= 50 for i in items)
        feed = c.get(f"/api/watch/{w['token']}/feed.xml")
        assert feed.headers["content-type"].startswith("application/atom+xml") and "<entry>" in feed.text
        assert c.post("/api/watch", json={"profile": prof, "webhook_url": "http://x"}).status_code == 422
        assert c.get("/api/watch/nope").status_code == 404


def test_deployments_both_sides():
    with _client() as c:
        o = c.get("/api/deployments", params={"side": "odbiorca", "budget": "wysoki"}).json()
        assert o["items"] and all(i["implementers"] and i["deploy_cost_pln"] > 0 for i in o["items"])
        w = c.get("/api/deployments", params={"side": "wykonawca"}).json()
        assert len(w["regions"]) == 16 and all(r["revenue_3y_pln"] >= 0 for r in w["regions"])


def test_partner_api_needs_key_and_limits(monkeypatch):
    monkeypatch.setenv("RADAR_PARTNER_KEYS", "k1")
    with _client() as c:
        assert c.get("/api/v1/ideas").status_code == 401
        assert c.get("/api/v1/ideas", headers={"X-API-Key": "zly"}).status_code == 401
        r = c.get("/api/v1/ideas", headers={"X-API-Key": "k1"})
        assert r.status_code == 200 and "items" in r.json()
        from radar.api import deals

        deals._BUCKETS["k1"] = [0.0, __import__("time").monotonic()]
        assert c.get("/api/v1/ideas", headers={"X-API-Key": "k1"}).status_code == 429


def test_clusters_three_ways():
    with _client() as c:
        t = c.get("/api/clusters").json()
        assert t["clusters"] and all(x["size"] >= 1 and len(x["maturity"]) == 4 and x["items"] for x in t["clusters"])
        assert [x["size"] for x in t["clusters"]] == sorted((x["size"] for x in t["clusters"]), reverse=True)
        r = c.get("/api/clusters", params={"mode": "rynki"}).json()
        assert r["clusters"] and all(x["adopters"] > 0 for x in r["clusters"])
        assert sum(x["size"] for x in r["clusters"]) == r["total"]
        p = c.get("/api/clusters", params={"mode": "podobne", "k": 3}).json()
        assert "clusters" in p
