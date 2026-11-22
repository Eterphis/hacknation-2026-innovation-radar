"""cards.pregen: pregenerated brief, slogan, business case and audience fit (issue #13, radar.pregen)

Revision ID: 0005
Revises: 0004
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "pregen" in {c["name"] for c in sa.inspect(op.get_bind()).get_columns("cards")}:  # newer create_all
        return
    with op.batch_alter_table("cards") as b:
        b.add_column(sa.Column("pregen", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("cards") as b:
        b.drop_column("pregen")
