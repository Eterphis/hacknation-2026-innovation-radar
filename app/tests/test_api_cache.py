"""Issue #31, etap 5: cache odczytów API (radar.api.cache) dla /api/match, /api/ideas, /api/clusters.
Drugie wywołanie nie robi ciężkich zapytań, nowa karta i polubienie są widoczne od razu, wynik z cache = wynik liczony."""

from contextlib import contextmanager

from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.engine import Engine

from radar.pipeline.tasks import harvest

MATCH = "/api/match?role=samorzady&voivodeship=pomorskie&budget=wysoki&goal=wdrozenie&limit=24"
IDEAS = "/api/ideas?limit=24&sort=score"
CLUSTERS = "/api/clusters?mode=rynki"


def _client(sources=("demo-zgloszenia", "demo-kohesio", "demo-publikacje")):
    for src in sources:
        harvest.apply((src,)).get()
    from radar.api.main import app

    return TestClient(app)


@contextmanager
def sql_count():
    n = {"n": 0}

    def count(*_a, **_k):
        n["n"] += 1

    event.listen(Engine, "before_cursor_execute", count)
    try:
        yield n
    finally:
        event.remove(Engine, "before_cursor_execute", count)


def test_second_call_only_checks_the_data_version():
    with _client() as c:
        for path in (MATCH, IDEAS, CLUSTERS):
            with sql_count() as first:
                a = c.get(path).json()
            with sql_count() as second:
                b = c.get(path).json()
            assert a == b, path
            assert second["n"] <= 2 < first["n"], (path, first["n"], second["n"])  # 2 = the data-version aggregates


def test_cached_answer_equals_a_freshly_computed_one():
    from radar.api.cache import STATS, reset_api_cache

    with _client() as c:
        cached = [c.get(p).json() for p in (MATCH, IDEAS, CLUSTERS)]
        cached = [c.get(p).json() for p in (MATCH, IDEAS, CLUSTERS)]  # second round is served from the cache
        assert STATS["hits"] >= 3
        reset_api_cache()
        fresh = [c.get(p).json() for p in (MATCH, IDEAS, CLUSTERS)]
        assert STATS["hits"] == 0  # really recomputed
        assert cached == fresh


def test_new_card_from_harvest_invalidates_the_cache():
    with _client(("demo-kohesio",)) as c:
        before = {p: c.get(p).json()["total"] for p in (MATCH, IDEAS, CLUSTERS)}
        harvest.apply(("demo-zgloszenia",)).get()  # the pipeline adds cards; no explicit invalidation call
        after = {p: c.get(p).json()["total"] for p in (MATCH, IDEAS, CLUSTERS)}
        assert all(after[p] > before[p] for p in before), (before, after)


def test_like_is_visible_immediately_in_the_card_and_in_lists():
    with _client() as c:
        item = c.get(IDEAS).json()["items"][0]
        cid, likes = item["card_id"], item["likes"]
        c.get(MATCH)  # warm the caches
        r = c.post(f"/api/cards/{cid}/like", headers={"X-Voter": "test-voter-cache-1"}).json()
        assert r == {"card_id": cid, "liked": True, "likes": likes + 1}
        assert c.get(f"/api/cards/{cid}").json()["likes"] == likes + 1
        assert next(i for i in c.get(IDEAS).json()["items"] if i["card_id"] == cid)["likes"] == likes + 1
        m = [i for i in c.get(MATCH).json()["items"] if i["card_id"] == cid]
        assert not m or m[0]["likes"] == likes + 1
        c.post(f"/api/cards/{cid}/like", headers={"X-Voter": "test-voter-cache-1"})  # toggles back
        assert c.get(f"/api/cards/{cid}").json()["likes"] == likes
        assert next(i for i in c.get(IDEAS).json()["items"] if i["card_id"] == cid)["likes"] == likes
