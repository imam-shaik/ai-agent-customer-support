"""phase 7 embeddings pgvector

Revision ID: 42e82a7e186e
Revises: 30229313bafb
Create Date: 2026-11-08 09:14:48.271234

Embeddings, pgvector and the knowledge_status CHECK deferred from the
Phase 6 amendment (SQLite could not take the constraint without a fragile
table recreate). Vector dimension 1024 is fixed by the selected embedding
model — see docs/PHASE7_REPORT.md §A; changing models with a different
dimension requires a follow-up migration.
"""

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


revision = '42e82a7e186e'
down_revision = '30229313bafb'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # pgvector provides the native vector type (no JSON arrays anywhere).
    # Requires a role with CREATE privilege on the database (local dev and
    # the test cluster use the superuser; managed Postgres needs the
    # extension provisioned or CREATE granted — documented in the report).
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # DB-level knowledge classification guard (Phase 6 decision #1).
    op.create_check_constraint(
        "ck_document_knowledge_status",
        "documents",
        "knowledge_status IN ('approved','challenge_fixture','archived')",
    )

    op.add_column(
        'document_chunks',
        sa.Column('embedding', Vector(1024), nullable=True),
    )
    op.add_column('document_chunks', sa.Column('embedding_model', sa.String(length=100), nullable=True))
    op.add_column('document_chunks', sa.Column('embedding_fingerprint', sa.String(length=64), nullable=True))
    op.add_column('document_chunks', sa.Column('embedded_at', sa.DateTime(timezone=True), nullable=True))
    # HNSW with cosine ops: no training pass (unlike IVFFlat), incremental
    # builds as the explicit indexing workflow writes vectors, and better
    # recall at this scale. Chosen deliberately — see report §B.
    op.create_index(
        'ix_document_chunks_embedding_hnsw',
        'document_chunks',
        ['embedding'],
        unique=False,
        postgresql_using='hnsw',
        postgresql_ops={'embedding': 'vector_cosine_ops'},
    )


def downgrade() -> None:
    op.drop_index('ix_document_chunks_embedding_hnsw', table_name='document_chunks', postgresql_using='hnsw', postgresql_ops={'embedding': 'vector_cosine_ops'})
    op.drop_column('document_chunks', 'embedded_at')
    op.drop_column('document_chunks', 'embedding_fingerprint')
    op.drop_column('document_chunks', 'embedding_model')
    op.drop_column('document_chunks', 'embedding')
    op.drop_constraint('ck_document_knowledge_status', 'documents', type_='check')
    # Extension left in place: dropping it would fail if anything else uses
    # it and is unnecessary for rollback of this revision's data model.
