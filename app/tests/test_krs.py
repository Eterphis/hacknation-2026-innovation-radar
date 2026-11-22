"""Issue #30 task 2: KRS profiles (trimmed real extracts as fixtures), spin-off linking, commercial signal."""

import json
from pathlib import Path

import httpx

from radar.sources import krs as K
from radar.sources.disk_cache import DiskCache

FIX = Path(__file__).parent / "fixtures" / "issue30"
PUT = json.loads((FIX / "krs_0000626339.json").read_text("utf-8"))
UTP = json.loads((FIX / "krs_0000728981.json").read_text("utf-8"))
POLITECHNIKA_POZNANSKA = {"name": "Politechnika Poznańska", "ids": {"regon": "000001608"}, "aliases": []}


def test_profile_has_legal_facts_with_source_and_date():
    p = K.company_profile(PUT, "2026-11-22T00:00:00+00:00")
    assert p["krs"] == "0000626339" and p["registered"] == "2016-07-01" and p["capital_pln"] == 5000.0
    assert p["voivodeship"] == "wielkopolskie" and p["pkd_main"]["code"] == "74.90.Z"
    assert p["shareholders"] == [{"name": "POLITECHNIKA POZNAŃSKA", "regon": "000001608", "krs": None, "whole": True}]
    assert p["source"].startswith("KRS") and p["fetched_at"] and not p["suspended"]
    assert K.company_profile(UTP)["suspended"] is True


def test_natural_person_shareholders_are_dropped():
    doc = json.loads(json.dumps(PUT))
    doc["odpis"]["dane"]["dzial1"]["wspolnicySpzoo"].append(
        {"nazwisko": {"nazwiskoICzlon": "KOWALSKI"}, "imiona": {"imie": "JAN"}, "posiadaneUdzialy": "1 UDZIAŁ"})
    p = K.company_profile(doc)
    assert len(p["shareholders"]) == 1 and "KOWALSKI" not in json.dumps(p, ensure_ascii=False)


def test_spinoff_linked_by_regon_krs_or_name():
    companies = [K.company_profile(PUT), K.company_profile(UTP)]
    assert [c["krs"] for c in K.spinoffs(companies, POLITECHNIKA_POZNANSKA)] == ["0000626339"]
    by_name = {"name": "Politechnika Bydgoska im. Jana i Jędrzeja Śniadeckich", "ids": {}}
    assert [c["krs"] for c in K.spinoffs(companies, by_name)] == ["0000728981"]
    assert K.spinoffs(companies, {"name": "Uniwersytet Rzeszowski", "ids": {"regon": "123456789"}}) == []


def test_commercial_signal_from_registry_and_fallback():
    fallback = {"route": None, "cue": None}
    sig = K.commercial_signal([K.company_profile(PUT, "2026-11-22T00:00:00+00:00")], fallback)
    assert "POLITECHNIKA INNOWACJE" in sig["route"] and "5 000 zł" in sig["route"]
    assert sig["registry"]["source"].startswith("KRS") and sig["registry"]["fetched_at"].startswith("2026-11-22")
    only_suspended = K.commercial_signal([K.company_profile(UTP)], fallback)
    assert "zawieszona" in only_suspended["route"]
    assert K.commercial_signal([], fallback) == {**fallback, "registry": None}


def test_client_cache_and_optional_failures(tmp_path):
    calls = []

    def handler(req):
        calls.append(str(req.url))
        if "0000626339" in str(req.url):
            return httpx.Response(200, json=PUT)
        if "0000000001" in str(req.url):
            return httpx.Response(404)
        return httpx.Response(500)

    c = K.KrsClient(cache=DiskCache("krs", root=tmp_path), http=httpx.Client(transport=httpx.MockTransport(handler)))
    got = K.fetch_many(c, ["626339", "0000000001", "0000999999"])
    assert [p["krs"] for p in got] == ["0000626339"]
    n = len(calls)
    assert c.odpis("0000626339")["name"].startswith("POLITECHNIKA") and len(calls) == n  # from disk


def test_committed_companies_file_is_real_and_personless():
    companies = K.load_companies()
    assert companies and all(c["source"].startswith("KRS") and c["fetched_at"] for c in companies)
    assert all(not any(k in json.dumps(h) for k in ("nazwisko", "imiona")) for c in companies for h in c["shareholders"])
