from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from radar.config import get_settings


class Base(DeclarativeBase):
    pass


_engine = None
_Session = None


def engine():
    global _engine, _Session
    if _engine is None:
        url = get_settings().database_url
        kwargs = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {"pool_pre_ping": True}
        _engine = create_engine(url, **kwargs)
        _Session = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def reset_engine() -> None:
    """Drop the cached engine (tests switch databases between runs)."""
    global _engine, _Session
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _Session = None


@contextmanager
def session():
    engine()
    s = _Session()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def create_all() -> None:
    """Tables straight from the models, no migration history: tests and throwaway SQLite files only."""
    from radar import models  # noqa: F401  (register tables)

    Base.metadata.create_all(engine())


def wait_for_db(timeout_s: float = 90.0, every_s: float = 2.0) -> None:
    """Block until the database accepts connections (pods start before Postgres is ready; crashing and being
    restarted by Kubernetes works too, but shows up as restarts and CrashLoopBackOff)."""
    import time

    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError

    deadline = time.monotonic() + timeout_s
    while True:
        try:
            with engine().connect() as c:
                c.execute(text("SELECT 1"))
            return
        except OperationalError:
            if time.monotonic() > deadline:
                raise
            time.sleep(every_s)


BASELINE = "0001"  # schema of the releases that used create_all (before T030)


def _alembic_cfg():
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", "radar:migrations")
    return cfg


def migrate(revision: str = "head") -> str:
    """Alembic upgrade (T030). A database created by the old create_all (tables, no alembic_version) is stamped
    at the baseline first, so existing deployments keep their data. Returns the revision now applied."""
    from alembic import command
    from alembic.runtime.migration import MigrationContext
    from sqlalchemy import inspect

    from alembic.autogenerate import compare_metadata

    from radar import models  # noqa: F401  (register tables)

    cfg = _alembic_cfg()
    with engine().connect() as conn:
        tables = set(inspect(conn).get_table_names())
        ctx = MigrationContext.configure(conn)
        current = ctx.get_current_revision()
        # tables but no history: made by create_all — of the baseline release, or (tests, demo) of these models
        up_to_date = current is None and "raw_records" in tables and not compare_metadata(ctx, Base.metadata)
    if current is None and "raw_records" in tables:
        command.stamp(cfg, "head" if up_to_date else BASELINE)
    command.upgrade(cfg, revision)
    with engine().connect() as conn:
        return MigrationContext.configure(conn).get_current_revision()
