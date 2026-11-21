"""Alembic environment: the URL comes from RADAR_DATABASE_URL (radar.config), the target is radar.models.

On PostgreSQL the upgrade holds an advisory lock, so the Helm migrate Job, `radar migrate` and an API pod
starting at the same moment cannot run the same revision twice.
"""

from alembic import context
from sqlalchemy import text

from radar import models  # noqa: F401  (register tables)
from radar.db import Base, engine

LOCK_ID = 727_202_611  # arbitrary, constant


def run() -> None:
    conn_cfg = context.config.attributes.get("connection")
    if conn_cfg is not None:
        _migrate(conn_cfg)
        return
    with engine().connect() as conn:
        _migrate(conn)


def _migrate(conn) -> None:
    pg = conn.dialect.name == "postgresql"
    if pg:
        conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": LOCK_ID})
    try:
        context.configure(connection=conn, target_metadata=Base.metadata, compare_type=True,
                          render_as_batch=conn.dialect.name == "sqlite")
        with context.begin_transaction():
            context.run_migrations()
    finally:
        if pg:
            conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": LOCK_ID})
            conn.commit()


run()
