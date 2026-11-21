"""T030: Alembic migrations match the models, and a pre-Alembic database is upgraded in place."""

from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect, text

from radar.db import Base, engine, migrate, reset_engine


def _fresh(tmp_path, monkeypatch, name):
    monkeypatch.setenv("RADAR_DATABASE_URL", f"sqlite:///{tmp_path / name}")
    from radar.config import get_settings

    get_settings.cache_clear()
    reset_engine()


def test_head_matches_models(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch, "m.db")
    assert migrate() == "0002"
    with engine().connect() as c:
        diff = compare_metadata(MigrationContext.configure(c, opts={"compare_type": True}), Base.metadata)
    assert diff == [], diff
    assert migrate() == "0002"  # idempotent


def test_legacy_create_all_database_is_stamped_and_upgraded(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch, "legacy.db")
    migrate("0001")
    with engine().begin() as c:  # what the old `create_all` left behind: tables, no alembic_version
        c.execute(text("DROP TABLE alembic_version"))
        c.execute(text("INSERT INTO settings (key, value, updated_at) VALUES ('keep', '{}', '2026-01-01')"))
    assert migrate() == "0002"
    with engine().connect() as c:
        assert "llm_calls" in inspect(c).get_table_names()
        assert "duration_ms" in {col["name"] for col in inspect(c).get_columns("stage_runs")}
        assert c.execute(text("SELECT count(*) FROM settings WHERE key='keep'")).scalar() == 1


def test_create_all_database_of_current_models_goes_to_head(tmp_path, monkeypatch):
    """Tests and demo files made by create_all of these models: stamped at head by the schema markers (no
    compare_metadata, whose dialect noise used to stamp 0001 and fail 0002 on the existing llm_calls)."""
    from radar.db import create_all

    _fresh(tmp_path, monkeypatch, "current.db")
    create_all()
    assert migrate() == "0002"


def test_half_migrated_database_is_finished_not_broken(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch, "half.db")
    migrate("0001")
    with engine().begin() as c:  # llm_calls present (newer create_all), duration_ms missing, no history
        c.execute(text("DROP TABLE alembic_version"))
        c.execute(text("CREATE TABLE llm_calls (id INTEGER PRIMARY KEY, provider VARCHAR(30) NOT NULL, model VARCHAR(120), "
                       "purpose VARCHAR(30) NOT NULL, ok BOOLEAN NOT NULL, latency_ms FLOAT NOT NULL, error VARCHAR(300), "
                       "tokens_in INTEGER, tokens_out INTEGER, created_at DATETIME NOT NULL)"))
    assert migrate() == "0002"
    with engine().connect() as c:
        assert "duration_ms" in {col["name"] for col in inspect(c).get_columns("stage_runs")}


def test_newest_schema_marker_is_head():
    from alembic.script import ScriptDirectory

    from radar.db import SCHEMA_MARKERS, _alembic_cfg

    assert SCHEMA_MARKERS[0][0] == ScriptDirectory.from_config(_alembic_cfg()).get_current_head()
