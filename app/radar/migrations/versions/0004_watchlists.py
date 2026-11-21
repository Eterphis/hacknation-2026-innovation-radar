"""watchlists: saved personalization profiles behind anonymous tokens (round 2, issue #23)

Revision ID: 0004
Revises: 0003
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "watchlists",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("token", sa.String(length=40), nullable=False),
        sa.Column("profile", sa.JSON(), nullable=False),
        sa.Column("min_match", sa.Integer(), nullable=False),
        sa.Column("webhook_url", sa.Text(), nullable=True),
        sa.Column("last_notified_card", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token"),
    )


def downgrade() -> None:
    op.drop_table("watchlists")
