"""staff reply gmail hand-off channel

Revision ID: a6f1d8c3e2b7
Revises: e7c2a9f4d5b3
Create Date: 2026-11-10 17:40:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "a6f1d8c3e2b7"
down_revision = "e7c2a9f4d5b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "staff_replies",
        sa.Column("dispatch_channel", sa.String(length=20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("staff_replies", "dispatch_channel")
