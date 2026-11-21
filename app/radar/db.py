from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from radar.config import get_settings


class Base(DeclarativeBase):
    pass


_engine = None
_Session = None


def _sqlite_pragmas(dbapi_conn, _record) -> None:
    """SQLite (laptop demo, several workers on one file): WAL lets readers run while one writer commits, and
    busy_timeout makes a second writer wait instead of failing at once with 'database is locked'."""
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA busy_timeout=30000")
    cur.close()


def engine():
    global _engine, _Session
    if _engine is None:
        url = get_settings().database_url
        kwargs = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {"pool_pre_ping": True}
        _engine = create_engine(url, **kwargs)
        if url.startswith("sqlite") and ":memory:" not in url and url.rstrip("/") != "sqlite:":
            event.listen(_engine, "connect", _sqlite_pragmas)
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


def _has_column(insp, table: str, column: str) -> bool:
    return table in insp.get_table_names() and column in {c["name"] for c in insp.get_columns(table)}


# A database made by create_all has tables but no alembic_version. It is stamped at the NEWEST revision whose
# marker is present, then upgraded. Concrete markers instead of a full metadata comparison: compare_metadata also
# reports dialect noise (types on SQLite), which used to stamp an up-to-date database at 0001 and make 0002 fail
# on an existing table. Every new migration adds its marker on top (test_migrations checks the newest is head).
SCHEMA_MARKERS: tuple[tuple[str, object], ...] = (
    ("0002", lambda insp: "llm_calls" in insp.get_table_names() and _has_column(insp, "stage_runs", "duration_ms")),
    (BASELINE, lambda insp: "raw_records" in insp.get_table_names()),
)


def detect_revision(conn) -> str | None:
    """Revision whose schema a history-less database already has (None: empty database)."""
    from sqlalchemy import inspect

    insp = inspect(conn)
    return next((rev for rev, probe in SCHEMA_MARKERS if probe(insp)), None)


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

    from radar import models  # noqa: F401  (register tables)

    cfg = _alembic_cfg()
    with engine().connect() as conn:
        current = MigrationContext.configure(conn).get_current_revision()
        found = detect_revision(conn) if current is None else None
    if found:  # tables but no history: made by create_all (baseline release, or tests/demo with these models)
        command.stamp(cfg, found)
    command.upgrade(cfg, revision)
    with engine().connect() as conn:
        return MigrationContext.configure(conn).get_current_revision()
