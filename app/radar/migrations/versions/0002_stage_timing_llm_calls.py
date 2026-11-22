"""stage timing and LLM call log (observability, issue #7)

Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent: a database may be half way (llm_calls made by a newer create_all, column missing, or the reverse);
    # radar.db.detect_revision stamps it at 0001 and this finishes the job instead of failing on an existing table.
    insp = sa.inspect(op.get_bind())
    if "llm_calls" not in insp.get_table_names():
        _create_llm_calls()
    if "duration_ms" not in {c["name"] for c in insp.get_columns("stage_runs")}:
        with op.batch_alter_table("stage_runs", schema=None) as batch_op:
            batch_op.add_column(sa.Column("duration_ms", sa.Float(), nullable=True))


def _create_llm_calls() -> None:
    op.create_table('llm_calls',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('provider', sa.String(length=30), nullable=False),
    sa.Column('model', sa.String(length=120), nullable=True),
    sa.Column('purpose', sa.String(length=30), nullable=False),
    sa.Column('ok', sa.Boolean(), nullable=False),
    sa.Column('latency_ms', sa.Float(), nullable=False),
    sa.Column('error', sa.String(length=300), nullable=True),
    sa.Column('tokens_in', sa.Integer(), nullable=True),
    sa.Column('tokens_out', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('llm_calls', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_llm_calls_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_llm_calls_provider'), ['provider'], unique=False)
        batch_op.create_index(batch_op.f('ix_llm_calls_purpose'), ['purpose'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("stage_runs", schema=None) as batch_op:
        batch_op.drop_column("duration_ms")
    with op.batch_alter_table('llm_calls', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_llm_calls_purpose'))
        batch_op.drop_index(batch_op.f('ix_llm_calls_provider'))
        batch_op.drop_index(batch_op.f('ix_llm_calls_created_at'))

    op.drop_table('llm_calls')
