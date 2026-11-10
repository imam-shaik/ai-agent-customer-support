"""Customer phone (optional) on escalation tickets.

Adds an OPTIONAL contact channel the customer may leave blank. Stored as
NULL when absent so "not provided" is never confused with an empty value.
"""

import sqlalchemy as sa
from alembic import op

revision = "d9e3f7a1b5c8"
down_revision = "c4f8a1d6e2b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tickets",
        sa.Column("customer_phone", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tickets", "customer_phone")
