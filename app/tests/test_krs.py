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
    assert c.odpis("0000626339")["fetched_at"]


def test_cache_keeps_only_the_cleaned_profile(tmp_path):
    raw = json.loads(json.dumps(PUT))
    raw["odpis"]["dane"]["dzial2"] = {"reprezentacja": {"sklad": [{"nazwisko": {"nazwiskoICzlon": "KOWALSKI"},
                                                                   "imiona": {"imie": "JAN"}}]}}
    c = K.KrsClient(cache=DiskCache("krs", root=tmp_path),
                    http=httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=raw))))
    assert c.odpis("0000626339")
    stored = "".join(p.read_text("utf-8") for p in (tmp_path / "krs").glob("*.json"))
    assert stored and "KOWALSKI" not in stored and "dzial2" not in stored and "POLITECHNIKA" in stored


def test_main_refuses_to_overwrite_with_a_partial_fetch(tmp_path, monkeypatch):
    seed = tmp_path / "seed.json"
    seed.write_text(json.dumps({"companies": [{"krs": "0000626339"}, {"krs": "0000728981"}]}), "utf-8")
    out = tmp_path / "companies.json"
    out.write_text("previous", "utf-8")
    monkeypatch.setattr(K, "fetch_many", lambda client, nums: [])  # KRS down
    assert K.main(["--seed", str(seed), "--out", str(out)]) == 1 and out.read_text("utf-8") == "previous"
    monkeypatch.setattr(K, "fetch_many", lambda client, nums: [{"krs": "0000626339"}])
    assert K.main(["--seed", str(seed), "--out", str(out), "--allow-partial"]) == 0
    assert json.loads(out.read_text("utf-8"))["companies"] == [{"krs": "0000626339", "seed_source": None}]


def test_committed_companies_file_is_real_and_personless():
    companies = K.load_companies()
    assert companies and all(c["source"].startswith("KRS") and c["fetched_at"] for c in companies)
    assert all(not any(k in json.dumps(h) for k in ("nazwisko", "imiona")) for c in companies for h in c["shareholders"])


def test_unreadable_200_is_not_cached(tmp_path):
    answers = [httpx.Response(200, json={"odpis": {}}), httpx.Response(200, json=PUT)]
    c = K.KrsClient(cache=DiskCache("krs", root=tmp_path),
                    http=httpx.Client(transport=httpx.MockTransport(lambda req: answers.pop(0))))
    assert K.fetch_many(c, ["626339"]) == []  # schema change / error page: skipped ...
    assert c.odpis("626339")["krs"] == "0000626339"  # ... and retried next time, not cached as "no company"
