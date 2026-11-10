"""Post-Phase-12 live-model migration: vector(1024) -> vector(2048).

Why: the originally selected models reached end-of-life on NVIDIA's API
(verified live 2026-11-10 with a real account key):
- embedding  nvidia/nv-embedqa-e5-v5      -> HTTP 410 (EOL 2026-08-25)
- chat       meta/llama-3.3-70b-instruct  -> HTTP 410 (EOL)

Replacements (probed live against the real API):
- embedding  nvidia/nemotron-3-embed-1b   -> 2048 dimensions, symmetric
- chat       deepseek-ai/deepseek-v4.1-flash -> strict-JSON verified

The pgvector column is widened 1024 -> 2048. ALL existing vectors were
produced by the retired model and are invalid for the replacement, so the
column is cleared (USING NULL) and every chunk returns to "pending" —
`scripts/index_knowledge.py` re-embeds everything with the new model
(vectors carry the model id; retrieval only ever searches same-model
vectors). The HNSW index must be dropped before the type change and is
rebuilt after.

Revision ID: c4f8a1d6e2b9
Revises: 7c1a9e4d2b60
"""

from alembic import op

revision = "c4f8a1d6e2b9"
down_revision = "7c1a9e4d2b60"
branch_labels = None
depends_on = None

HNSW_INDEX = "ix_document_chunks_embedding_hnsw"


def _rebuild_index_1024() -> None:
    op.execute(f"CREATE INDEX {HNSW_INDEX} ON document_chunks USING hnsw (embedding vector_cosine_ops)")


def upgrade() -> None:
    # No index rebuild on upgrade: pgvector's HNSW index caps at 2000
    # dimensions, so vector(2048) cannot carry the old HNSW index. At MVP
    # corpus scale the exact sequential cosine scan is the right trade —
    # correct, index-free, and fast for hundreds of chunks.
    op.execute(f"DROP INDEX IF EXISTS {HNSW_INDEX}")
    op.execute("ALTER TABLE document_chunks ALTER COLUMN embedding TYPE vector(2048) USING NULL")


def downgrade() -> None:
    # 1024 dims CAN carry HNSW, so the original index is restored on the
    # way down (vectors are NULLed either way and need re-embedding).
    op.execute(f"DROP INDEX IF EXISTS {HNSW_INDEX}")
    op.execute("ALTER TABLE document_chunks ALTER COLUMN embedding TYPE vector(1024) USING NULL")
    _rebuild_index_1024()
