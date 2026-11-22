"""organisation registry (RAD-on institutions, issue #5)

Revision ID: 0003
Revises: 0002
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "organizations" in sa.inspect(op.get_bind()).get_table_names():  # made by a newer create_all
        return
    op.create_table(
        "organizations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("ids", sa.JSON(), nullable=False),
        sa.Column("institution_type", sa.String(length=30), nullable=True),
        sa.Column("is_public", sa.Boolean(), nullable=True),
        sa.Column("voivodeship", sa.String(length=40), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=True),
        sa.Column("aliases", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
    )


def downgrade() -> None:
    op.drop_table("organizations")
