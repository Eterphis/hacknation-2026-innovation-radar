"""Dedup (T025): the fullest record of a cluster is canonical, whatever the harvest order; sources with
`group_by_title` (Kohesio) group projects of one programme by title across years."""

import json

import pytest
from sqlalchemy import select

from radar.db import session
from radar.models import Record
from radar.pipeline.tasks import completeness, harvest, reconcile_all

BODY = ("Opracowano system czujników IoT i aplikację, która w czasie rzeczywistym monitoruje jakość wody w sieci "
        "wodociągowej gminy. Rozwiązanie przetestowano w pilotażu w dwóch gminach i wdrożono u beneficjenta. ")
THIN = {"id": "thin-1", "title": "Inteligentny monitoring jakości wody w gminach", "abstract": BODY, "year": 2023}
FULL = {"id": "full-1", "title": "Inteligentny monitoring jakości wody w gminach", "year": 2023,
        "abstract": BODY * 3, "doi": "10.1234/woda.2023.1", "orgs": ["Politechnika Rzeszowska", "Gmina Krasne"],
        "keywords": ["woda", "IoT", "monitoring"], "url": "https://example.org/woda", "amount": "2 450 000,00"}

SOURCES = """
sources:
  - id: src-a
    type: snapshot
    kind: project
    options: {{ path: "{dir}/a.jsonl", optional: true, min_abstract_chars: 100 }}
    id_path: id
    mapping: &m
      title: title
      abstract: abstract
      year: year
      doi: doi
      url: url
      affiliations: orgs
      keywords: keywords
      region: region
      amount_total: {{ expr: amount, transform: pl_decimal }}
  - id: src-b
    type: snapshot
    kind: project
    options: {{ path: "{dir}/b.jsonl", optional: true, min_abstract_chars: 100 }}
    id_path: id
    mapping: *m
  - id: kohesio
    type: snapshot
    kind: project
    options: {{ path: "{dir}/k.jsonl", optional: true, min_abstract_chars: 100, group_by_title: true }}
    id_path: id
    mapping: *m
"""


@pytest.fixture
def sources(tmp_path, monkeypatch):
    f = tmp_path / "sources.yaml"
    f.write_text(SOURCES.format(dir=tmp_path.as_posix()), encoding="utf-8")
    monkeypatch.setenv("RADAR_SOURCES_FILE", str(f))
    from radar.config import get_settings

    get_settings.cache_clear()

    def write(name, *items):
        (tmp_path / f"{name}.jsonl").write_text("\n".join(json.dumps(i, ensure_ascii=False) for i in items) + "\n",
                                                encoding="utf-8")
    return write


def _state():
    with session() as s:
        return {s.get(Record, r.id).raw.external_id: (r.status, r.cluster_id, r.id, (r.extra or {}).get("cluster_size"))
                for r in s.scalars(select(Record))}


@pytest.mark.parametrize("order", [("thin", "full"), ("full", "thin")])
def test_fullest_record_is_canonical_in_any_order(sources, order):
    items = {"thin": ("a", THIN), "full": ("b", FULL)}
    for key in order:
        name, item = items[key]
        sources(name, item)
        harvest.apply((f"src-{name}",)).get()
    st = _state()
    assert st["thin-1"][0] == "duplicate"
    assert st["full-1"][0] != "duplicate"
    full_id = st["full-1"][2]
    assert st["thin-1"][1] == full_id and st["full-1"][1] == full_id  # cluster = canonical id
    assert st["full-1"][3] == 2
    assert reconcile_all() == 0  # the demoted record is terminal, nothing re-enqueued


def test_demoted_record_card_is_hidden(sources):
    sources("a", THIN)
    harvest.apply(("src-a",)).get()
    with session() as s:
        thin = s.scalar(select(Record).where(Record.source_id == "src-a"))
        had_card = thin.card is not None
    sources("b", FULL)
    harvest.apply(("src-b",)).get()
    with session() as s:
        thin = s.scalar(select(Record).where(Record.source_id == "src-a"))
        assert thin.status == "duplicate" and "pełniejszy" in thin.review_reasons[0]
        if had_card:
            assert thin.card.hidden


def test_kohesio_projects_with_the_same_title_form_one_group(sources):
    title = "Czyste powietrze – wymiana wysokoemisyjnych źródeł ciepła w budynkach mieszkalnych"
    desc = ("Projekt obejmuje wymianę wysokoemisyjnych źródeł ciepła na pompy ciepła i kotły gazowe w budynkach "
            "mieszkalnych na terenie gminy, co ograniczy niską emisję i poprawi jakość powietrza.")
    sources("k",
            {"id": "Q1", "title": title, "abstract": desc, "year": 2019, "orgs": ["Gmina A"]},
            {"id": "Q2", "title": title.upper().replace("–", "-"), "abstract": desc * 2, "year": 2022,
             "orgs": ["Gmina B"], "region": "dolnośląskie", "amount": "1 200 000,00"},
            {"id": "Q3", "title": title, "abstract": desc, "year": 2024, "orgs": ["Gmina C"]},
            {"id": "Q4", "title": "Budowa ścieżki rowerowej wzdłuż rzeki w gminie", "abstract": desc, "year": 2022})
    harvest.apply(("kohesio",)).get()
    st = _state()
    canonical = [k for k in ("Q1", "Q2", "Q3") if st[k][0] != "duplicate"]
    assert canonical == ["Q2"]  # the fullest one, although harvested second
    assert {st[k][1] for k in ("Q1", "Q2", "Q3")} == {st["Q2"][2]}
    assert st["Q2"][3] == 3
    assert st["Q4"][0] != "duplicate"


def test_same_title_in_ordinary_source_needs_close_years(sources):
    sources("a", {**THIN, "id": "x1", "year": 2015}, {**THIN, "id": "x2", "year": 2023})
    harvest.apply(("src-a",)).get()
    st = _state()
    assert st["x1"][0] != "duplicate" and st["x2"][0] != "duplicate"


def test_completeness_prefers_richer_records():
    thin = Record(title="t", abstract="x" * 300)
    rich = Record(title="t", abstract="x" * 300, doi="10.1/x", affiliations=["A"], keywords=["k"], amounts={"amount_total": 1.0})
    assert completeness(rich) > completeness(thin)
