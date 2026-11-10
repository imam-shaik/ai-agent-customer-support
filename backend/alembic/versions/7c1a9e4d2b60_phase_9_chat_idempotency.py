"""phase 9 chat idempotency

Revision ID: 7c1a9e4d2b60
Revises: 42e82a7e186e
Create Date: 2026-11-09

Phase 9 turn idempotency:
- `client_request_id` identifies one customer submission; the partial
  unique index guarantees one user row per request per conversation.
- `reply_to_message_id` binds an assistant reply to exactly one customer
  turn; the partial unique index guarantees at most one assistant reply
  per turn even under concurrent retries.
Both columns are nullable, so existing rows and legacy clients are
unaffected (no backfill, no downtime).
"""

from alembic import op
import sqlalchemy as sa


revision = '7c1a9e4d2b60'
down_revision = '42e82a7e186e'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'messages',
        sa.Column('client_request_id', sa.String(length=36), nullable=True),
    )
    op.add_column(
        'messages',
        sa.Column('reply_to_message_id', sa.String(length=32), nullable=True),
    )
    op.create_foreign_key(
        'fk_messages_reply_to_message',
        'messages',
        'messages',
        ['reply_to_message_id'],
        ['id'],
        ondelete='SET NULL',
    )
    op.create_index(
        'uq_messages_conversation_client_request',
        'messages',
        ['conversation_id', 'client_request_id'],
        unique=True,
        postgresql_where=sa.text('client_request_id IS NOT NULL'),
    )
    op.create_index(
        'uq_messages_reply_to',
        'messages',
        ['reply_to_message_id'],
        unique=True,
        postgresql_where=sa.text('reply_to_message_id IS NOT NULL'),
    )


def downgrade() -> None:
    op.drop_index('uq_messages_reply_to', table_name='messages')
    op.drop_index('uq_messages_conversation_client_request', table_name='messages')
    op.drop_constraint('fk_messages_reply_to_message', 'messages', type_='foreignkey')
    op.drop_column('messages', 'reply_to_message_id')
    op.drop_column('messages', 'client_request_id')
