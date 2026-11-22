"""Issue #30 task 1: EPO OPS client (fixtures, no network), harvester adapter, matching and the ip signal."""

import json
from pathlib import Path

import httpx

from radar.sources import epo_ops as E
from radar.sources.disk_cache import DiskCache

FIX = Path(__file__).parent / "fixtures"
SEARCH = json.loads((FIX / "issue30" / "epo_ops_search.json").read_text("utf-8"))


def test_parse_search_keeps_no_personal_data():
    assets = E.parse_search(SEARCH, fetched_at="2026-11-22T00:00:00+00:00")
    assert [a["publication"] for a in assets] == ["PL999001B1", "PL445566A1", "WO2024123456A1"]
    assert [a["status"] for a in assets] == ["granted", "filed", "filed"]
    assert assets[0]["date"] == "2024-03-15" and assets[0]["titles"]["pl"].startswith("Sposób")
    assert all(a["source"] == "EPO OPS" and a["fetched_at"] and a["url"].startswith("https://worldwide.espacenet.com")
               for a in assets)
    dumped = json.dumps(assets, ensure_ascii=False)
    assert "KOWALSKI" not in dumped and "applicant" not in dumped


def test_kind_codes():
    assert E.status_of("PL", "B1") == "granted" and E.status_of("EP", "B2") == "granted"
    assert E.status_of("PL", "A1") == "filed" and E.status_of("WO", "A1") == "filed"
    assert E.status_of("PL", "Y1") == "utility_model" and E.status_of("PL", "U1") == "utility_model_filed"


def test_no_key_means_no_client(monkeypatch):
    monkeypatch.delenv("RADAR_EPO_OPS_KEY", raising=False)
    monkeypatch.delenv("RADAR_EPO_OPS_SECRET", raising=False)
    assert E.EpoOps.from_env() is None
    assert E.harvest_orgs(None, [("radon:1", "Politechnika Rzeszowska")]) == {}


def test_client_auth_search_and_disk_cache(tmp_path):
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req.url.path)
        if req.url.path.endswith("/auth/accesstoken"):
            assert req.headers["Authorization"].startswith("Basic ")
            return httpx.Response(200, json={"access_token": "t0k", "expires_in": "1199"})
        assert req.headers["Authorization"] == "Bearer t0k" and 'pa="Politechnika Rzeszowska"' in str(req.url.params["q"])
        return httpx.Response(200, json=SEARCH)

    http = httpx.Client(transport=httpx.MockTransport(handler))
    c = E.EpoOps("k", "s", cache=DiskCache("epo_ops", root=tmp_path), http=http)
    got = E.harvest_orgs(c, [("radon:1", "Politechnika Rzeszowska")])
    assert len(got["radon:1"]["assets"]) == 3 and all(a["org_key"] == "radon:1" for a in got["radon:1"]["assets"])
    n = len(calls)
    E.harvest_orgs(c, [("radon:1", "Politechnika Rzeszowska")])  # second run: from disk, no request
    assert len(calls) == n


def test_failing_org_is_skipped(tmp_path):
    http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(503)))
    c = E.EpoOps("k", "s", cache=DiskCache("epo_ops", root=tmp_path), http=http)
    assert E.harvest_orgs(c, [("radon:1", "X")]) == {}


def test_matching_by_title_stems():
    assets = E.parse_search(SEARCH)
    m = E.match_record("Kompozyt do magazynowania wodoru dla pojazdów", ["wodór"], assets)
    assert m and m[0]["publication"] == "PL999001B1" and m[0]["match"] >= 0.5
    assert E.match_record("System rezerwacji wizyt w urzędzie gminy", [], assets) == []


def test_ip_signal_registry_beats_text_and_falls_back():
    assets = [{**a, "fetched_at": "2026-11-22T00:00:00+00:00"} for a in E.parse_search(SEARCH)]
    fallback = {"strength": "none", "in_text": None, "org_patents": 0, "examples": []}
    matched = E.match_record("Kompozyt do magazynowania wodoru", [], assets)
    ip = E.ip_signal(assets, matched, fallback)
    assert ip["strength"] == "strong" and ip["registry"]["source"] == "EPO OPS"
    assert ip["registry"]["fetched_at"].startswith("2026-11-22") and ip["registry"]["granted"] == 1
    assert E.ip_signal(assets, [], fallback)["strength"] == "weak"
    assert E.ip_signal(assets, [], {**fallback, "strength": "medium"})["strength"] == "medium"
    assert E.ip_signal([], [], fallback) == {**fallback, "registry": None}


def test_harvester_records_become_assets():
    rec = json.loads((FIX / "harvester" / "uprp_import.jsonl").read_text("utf-8").splitlines()[0])
    a = E.assets_from_harvest(rec)
    assert a["country"] == "PL" and a["status"] in ("granted", "filed", "utility_model", "utility_model_filed")
    assert a["titles"] and a["organizations"] and "POLITECHNIKA" in a["organizations"][0].upper()
    assert E.assets_from_harvest({"title": "x"}) is None


def test_quota_answer_stops_the_run(tmp_path):
    seen = []

    def handler(req):
        if req.url.path.endswith("/accesstoken"):
            return httpx.Response(200, json={"access_token": "t", "expires_in": "1200"})
        seen.append(req.url.params["q"])
        return httpx.Response(403, headers={"X-Rejection-Reason": "IndividualQuotaPerHour"})

    c = E.EpoOps("k", "s", cache=DiskCache("epo_ops", root=tmp_path), http=httpx.Client(transport=httpx.MockTransport(handler)))
    assert E.harvest_orgs(c, [("a", "A"), ("b", "B"), ("c", "C")]) == {}
    assert len(seen) == 1  # no more requests after the quota answer
