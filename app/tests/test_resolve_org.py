"""T023: organisation registry from RAD-on institutions and the resolve_org stage."""

import json

import pytest
from sqlalchemy import select

from radar.db import session
from radar.models import Organization, Record
from radar.orgs import Matcher, OrgInfo, registry_row, resolve, summary
from radar.pipeline.tasks import harvest

# rows in the format radar.sources.radon writes to radon_institutions.jsonl (values from the live registry)
INSTITUTIONS = [
    {"uuid": "u-prz", "name": "Politechnika Rzeszowska im. Ignacego Łukasiewicza", "regon": "000001583", "nip": "8130201234",
     "krs": None, "kind": "Uczelnia publiczna", "type_hint": "university", "is_public": True, "status": "Działająca",
     "voivodeship": "podkarpackie", "city": "Rzeszów", "former_names": []},
    {"uuid": "u-agh", "name": "Akademia Górniczo-Hutnicza im. Stanisława Staszica w Krakowie", "regon": "000001310",
     "kind": "Uczelnia publiczna", "type_hint": "university", "is_public": True, "voivodeship": "małopolskie",
     "city": "Kraków", "former_names": []},
    {"uuid": "u-umlodz", "name": "Uniwersytet Medyczny w Łodzi", "kind": "Uczelnia publiczna", "type_hint": "university",
     "is_public": True, "voivodeship": "łódzkie", "city": "Łódź", "former_names": []},
    {"uuid": "u-umlub", "name": "Uniwersytet Medyczny w Lublinie", "kind": "Uczelnia publiczna", "type_hint": "university",
     "is_public": True, "voivodeship": "lubelskie", "city": "Lublin", "former_names": []},
    {"uuid": "u-ilot", "name": "Sieć Badawcza Łukasiewicz - Instytut Lotnictwa", "kind": "Instytucja naukowa",
     "subtype": "instytut Sieci Łukasiewicz", "type_hint": "research_institute", "is_public": True,
     "voivodeship": "mazowieckie", "city": "Warszawa", "former_names": ["Instytut Lotnictwa"]},
    {"uuid": "u-ien", "name": "Instytut Energetyki – Państwowy Instytut Badawczy", "kind": "Instytucja naukowa",
     "type_hint": "research_institute", "is_public": True, "voivodeship": "mazowieckie", "city": "Warszawa",
     "former_names": ["Instytut Energetyki - Instytut Badawczy"]},
    {"uuid": "u-wsp", "name": "Wyższa Praska Szkoła Biznesu - w likwidacji z siedzibą w Warszawie", "kind": "Uczelnia niepubliczna",
     "type_hint": "university", "is_public": False, "voivodeship": "mazowieckie", "city": "Warszawa", "former_names": []},
    {"uuid": "u-wss", "name": "Wojewódzki Szpital Specjalistyczny we Wrocławiu", "kind": "Instytucja naukowa",
     "type_hint": "research_institute", "is_public": True, "voivodeship": "dolnośląskie", "city": "Wrocław", "former_names": []},
    {"uuid": "u-umcs", "name": "Uniwersytet Marii Curie-Skłodowskiej w Lublinie", "kind": "Uczelnia publiczna",
     "type_hint": "university", "is_public": True, "voivodeship": "lubelskie", "city": "Lublin", "former_names": []},
    {"uuid": "u-ansb", "name": "Akademia Nauk Stosowanych w Skierniewicach", "kind": "Uczelnia publiczna",
     "type_hint": "university", "is_public": True, "voivodeship": "łódzkie", "city": "Skierniewice",
     "former_names": ["Państwowa Uczelnia Zawodowa w Skierniewicach"]},
]


@pytest.fixture
def matcher():
    rows = [registry_row(i) for i in INSTITUTIONS]
    return Matcher([OrgInfo(id=n, name=r["name"], ids=r["ids"], institution_type=r["institution_type"],
                            is_public=r["is_public"], voivodeship=r["voivodeship"], city=r["city"])
                    for n, r in enumerate(rows)], {n: r["aliases"] for n, r in enumerate(rows)})


@pytest.mark.parametrize("affiliation,expected,method", [
    ("Politechnika Rzeszowska", "Politechnika Rzeszowska im. Ignacego Łukasiewicza", "alias"),
    ("Wydział Chemiczny Politechniki Rzeszowskiej", "Politechnika Rzeszowska im. Ignacego Łukasiewicza", "contains"),
    ("AGH", "Akademia Górniczo-Hutnicza im. Stanisława Staszica w Krakowie", "acronym"),
    ("Akademia Górniczo-Hutnicza w Krakowie", "Akademia Górniczo-Hutnicza im. Stanisława Staszica w Krakowie", "alias"),
    ("Instytut Lotnictwa", "Sieć Badawcza Łukasiewicz - Instytut Lotnictwa", "alias"),
    ("Uniwersytet Medyczny w Łodzi, Zakład Biofizyki", "Uniwersytet Medyczny w Łodzi", "alias"),
    ("Plitechnika Rzeszowska", "Politechnika Rzeszowska im. Ignacego Łukasiewicza", "fuzzy"),
])
def test_cascade_finds_the_institution(matcher, affiliation, expected, method):
    r = matcher.match(affiliation)
    assert (r["org_name"], r["method"]) == (expected, method)
    assert r["accepted"] and r["confidence"] >= 0.90


@pytest.mark.parametrize("affiliation", [
    "Uniwersytet Medyczny",                     # two entries share the short form: identifies neither
    "Państwowa Uczelnia Zawodowa w Tarnowie",   # generic former name of an entry in another city
    "Gmina Krasne",                             # municipalities are not in RAD-on
    # false matches seen on live RAD-on project data (2026-11-21), now refused:
    "NASK Państwowy Instytut Badawczy z siedzibą w Warszawie",            # generic tail of another institute
    "Instytut Badawczy Norwegii Zachodniej",                              # "Instytut Badawczy" alone
    "KenBIT Spółka z ograniczoną odpowiedzialnością, z siedzibą w Warszawie",  # company, generic "z siedzibą"
    "Wojewódzki Szpital Specjalistyczny im. J. Gromkowskiego",            # name without city = a class of hospitals
    "Fundacja Absolwentów UMCS",                                          # acronym of someone else's body
    "TYMBARK-MWS sp z o.o.",
    "APS Energia SA",
])
def test_no_guess_when_unsure(matcher, affiliation):
    assert not matcher.match(affiliation)["accepted"]


def test_ids_from_the_harvester_win(matcher):
    r = matcher.match("PRz", {"regon": "000001583"})
    assert (r["org_name"], r["method"], r["confidence"]) == ("Politechnika Rzeszowska im. Ignacego Łukasiewicza", "id", 1.0)
    r = matcher.match("dowolna nazwa", {"radon_uuid": "u-agh"})
    assert r["method"] == "id" and r["voivodeship"] == "małopolskie"


def test_summary_takes_the_first_sure_organisation(matcher):
    res = resolve(matcher, ["Gmina Krasne", "Politechnika Rzeszowska", "AGH"], None)
    assert [r["accepted"] for r in res] == [False, True, True]
    assert summary(res) == {"org_id": 0, "institution_type": "uczelnia", "is_public": True, "voivodeship": "podkarpackie"}


RECORD = {
    "schema": "radar.record/v1", "source": "radon_projects", "record_id": "radon-1", "title": "Lekkie kompozyty dla lotnictwa",
    "text_for_llm": "Projekt opracowuje lekkie kompozyty polimerowe do konstrukcji lotniczych. Zespół przygotował "
                    "prototyp elementu poszycia i przebadał go w laboratorium. Wyniki zostaną przekazane do przemysłu "
                    "lotniczego w regionie i do partnerów w Dolinie Lotniczej.",
    "organizations": [{"name": "Politechnika Rzeszowska im. Ignacego Łukasiewicza", "radon_uuid": "u-prz"},
                      {"name": "Firma Kompozyt sp. z o.o."}],
    "period": {"start": "2024-01-01"}, "region": {"voivodeships": []}, "keywords": ["kompozyty"],
    "funding": {"total_value": "1 200 000,00"}, "rights": {"licence": "CC0"}, "quality": {"status": "ok"},
}


def test_pipeline_loads_registry_and_resolves(tmp_path, monkeypatch):
    reg = tmp_path / "radon_institutions.jsonl"
    reg.write_text("\n".join(json.dumps(i, ensure_ascii=False) for i in INSTITUTIONS) + "\n", encoding="utf-8")
    (tmp_path / "radon.jsonl").write_text(json.dumps(RECORD, ensure_ascii=False) + "\n", encoding="utf-8")
    monkeypatch.setenv("RADAR_HARVEST_DIR", str(tmp_path))
    monkeypatch.setenv("RADAR_ORG_REGISTRY", str(reg))
    harvest.apply(("harvester-radon",)).get()
    with session() as s:
        assert len(s.scalars(select(Organization)).all()) == len(INSTITUTIONS)
        r = s.scalar(select(Record).where(Record.source_id == "harvester-radon"))
        orgs = r.extra["orgs"]
        assert orgs[0]["method"] == "id" and orgs[0]["accepted"]
        assert not orgs[1]["accepted"]  # a company: not in the registry, no guess
        assert r.extra["institution_type"] == "uczelnia" and r.extra["is_public"] is True
        assert r.region == "podkarpackie" and r.voivodeship == "podkarpackie"
        assert r.institution_type == "uczelnia"  # Basal took the registry's type


def test_without_registry_affiliations_pass_through(tmp_path, monkeypatch):
    (tmp_path / "radon.jsonl").write_text(json.dumps(RECORD, ensure_ascii=False) + "\n", encoding="utf-8")
    monkeypatch.setenv("RADAR_HARVEST_DIR", str(tmp_path))
    harvest.apply(("harvester-radon",)).get()
    with session() as s:
        r = s.scalar(select(Record).where(Record.source_id == "harvester-radon"))
        assert "orgs" not in (r.extra or {})
