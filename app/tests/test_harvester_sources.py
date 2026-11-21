"""Contract per source: the files radar.refresh writes for OpenAlex, Interreg, CORDIS, FE 2021-2027 and the UPRP
manual import enter the app through their `harvester-*` snapshot source. No network.

The fixtures in tests/fixtures/harvester/ are the real output of the harvester connectors (radar/sources/*) run
offline on their own test inputs (tests/fixtures/<source>/ in the repo root), two records each."""

import shutil
from pathlib import Path

import pytest
from sqlalchemy import select

from radar.db import session
from radar.models import Record
from radar.pipeline.tasks import harvest

FIXTURES = Path(__file__).parent / "fixtures" / "harvester"

# app source id -> (file radar.refresh writes, `source` the connector stamps on its records)
SOURCES = {
    "harvester-openalex": ("openalex.jsonl", "openalex_pl"),
    "harvester-interreg": ("interreg.jsonl", "interreg_pl"),
    "harvester-cordis": ("cordis.jsonl", "cordis_pl"),
    "harvester-fe": ("fe_projects.jsonl", "fe_2021_2027"),
    "harvester-uprp": ("uprp_import.jsonl", "uprp_pl"),
}


@pytest.mark.parametrize("source_id", sorted(SOURCES))
def test_source_output_loads_into_the_app(source_id, tmp_path, monkeypatch):
    fname, harvester_source = SOURCES[source_id]
    shutil.copy(FIXTURES / fname, tmp_path / fname)
    monkeypatch.setenv("RADAR_HARVEST_DIR", str(tmp_path))
    out = harvest.apply((source_id,)).get()
    assert out["accepted"] >= 1, out
    with session() as s:
        recs = s.scalars(select(Record).where(Record.source_id == source_id)).all()
        assert recs, f"{source_id}: no records in the database"
        for r in recs:
            assert r.title and r.abstract
            assert r.extra["harvester_source"] == harvester_source


def test_harvester_sources_cover_the_brief():
    """At least 8 distinct live sources are wired into the app (the demo ones do not count)."""
    from radar.sources.registry import load_sources

    live = [s for s in load_sources().values() if s.id.startswith("harvester-") and s.enabled]
    assert len(live) >= 8, [s.id for s in live]
    assert set(SOURCES) <= {s.id for s in live}
