"""staff reply composer table

Revision ID: e7c2a9f4d5b3
Revises: b8e4f2a6c9d1
Create Date: 2026-11-10 15:10:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "e7c2a9f4d5b3"
down_revision = "b8e4f2a6c9d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "staff_replies",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column(
            "ticket_id",
            sa.String(length=32),
            sa.ForeignKey("tickets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("staff_name", sa.String(length=100), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("sent_to", sa.String(length=320), nullable=False),
        sa.Column("email_dispatched", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("dispatch_note", sa.String(length=300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_staff_replies_ticket_id", "staff_replies", ["ticket_id"])


def downgrade() -> None:
    op.drop_index("ix_staff_replies_ticket_id", table_name="staff_replies")
    op.drop_table("staff_replies")
