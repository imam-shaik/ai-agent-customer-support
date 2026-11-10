"""Retrieval-quality migration: vector(2048) -> vector(4096).

Why: the previous embedding model (nvidia/nemotron-3-embed-1b, symmetric)
produced a nearly flat cosine band — on-topic and unrelated passage pairs
scored within ~0.04 of each other, so ranking could not surface the
on-topic chunk once the corpus grew (measured live 2026-11-10, see
scripts/probe_embedding_models.py).

Replacement (probed live against the real API):
- embedding  nvidia/nemotron-3.5-embed-8b -> 4096 dimensions, ASYMMETRIC
  (requires input_type=query|passage, sent by the provider per role),
  discrimination margin ~0.30 on the same probe (vs ~0.04), reliable at
  batch=1 (the endpoint 500s on multi-item batches, so batch size is 1).

The pgvector column is widened 2048 -> 4096. ALL existing vectors were
produced by the retired model and are invalid for the replacement, so the
column is cleared (USING NULL) and every chunk returns to "pending" —
`scripts/index_knowledge.py --force` re-embeds everything with the new
model (vectors carry the model id; retrieval only ever searches
same-model vectors). The HNSW index stays absent: 4096 dimensions are
still above pgvector's 2000-dimension HNSW cap.

Revision ID: b7e2f9a4c1d3
Revises: a6f1d8c3e2b7
"""

from alembic import op

revision = "b7e2f9a4c1d3"
down_revision = "a6f1d8c3e2b7"
branch_labels = None
depends_on = None

HNSW_INDEX = "ix_document_chunks_embedding_hnsw"


def upgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {HNSW_INDEX}")
    op.execute(
        "ALTER TABLE document_chunks ALTER COLUMN embedding TYPE vector(4096) USING NULL"
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {HNSW_INDEX}")
    op.execute(
        "ALTER TABLE document_chunks ALTER COLUMN embedding TYPE vector(2048) USING NULL"
    )
