"""staff authentication tables

Revision ID: b8e4f2a6c9d1
Revises: d9e3f7a1b5c8
Create Date: 2026-11-10 09:30:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "b8e4f2a6c9d1"
down_revision = "d9e3f7a1b5c8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "staff_users",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_staff_users_email", "staff_users", ["email"], unique=True)

    op.create_table(
        "staff_sessions",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column(
            "token_hash", sa.String(length=64), nullable=False
        ),
        sa.Column(
            "user_id",
            sa.String(length=32),
            sa.ForeignKey("staff_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_staff_sessions_token_hash", "staff_sessions", ["token_hash"], unique=True)
    op.create_index("ix_staff_sessions_user_id", "staff_sessions", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_staff_sessions_user_id", table_name="staff_sessions")
    op.drop_index("ix_staff_sessions_token_hash", table_name="staff_sessions")
    op.drop_table("staff_sessions")
    op.drop_index("ix_staff_users_email", table_name="staff_users")
    op.drop_table("staff_users")
