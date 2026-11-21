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
