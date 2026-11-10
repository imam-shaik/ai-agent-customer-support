"""Explicit indexing workflow (Phase 7 §8).

    READY document → eligible chunks → embedding provider → pgvector

Invoked ONLY by scripts/index_knowledge.py or tests — never at
application startup, and never during a search request (search embeds the
query and nothing else).

Safety rules encoded here:
- Only READY documents whose knowledge_status is indexable
  ("approved" + the labeled "challenge_fixture"; "archived" is never
  indexed — see INDEXABLE_KNOWLEDGE_STATUSES).
- Embedding identity is content-derived (document content hash + chunk
  index + chunk content hash), never row ids, so unchanged chunks are
  reused and changed chunks are re-embedded.
- A failed batch rolls back and raises: affected chunks keep their old
  (or NULL) embedding and stay un-searchable instead of pretending.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.embeddings import (
    EmbeddingProvider,
    EmbeddingProviderError,
    ensure_configured_dimensions,
    get_embedding_provider,
)
from app.models.entities import Document, DocumentChunk

logger = get_logger("app.indexing")

# Indexing scope (documented strategy, Phase 7 §8): approved knowledge and
# the clearly-labeled challenge fixtures — fixtures must be embedded to be
# retrievable through the controlled conflict-test path. "archived" is
# never indexed; if a document is un-archived later, the next run picks it
# up automatically.
INDEXABLE_KNOWLEDGE_STATUSES = ("approved", "challenge_fixture")


def chunk_fingerprint(
    document_content_hash: str, chunk_index: int, chunk_content: str
) -> str:
    """Content-derived embedding identity (Phase 6 directive #2).

    sha256(document.content_hash : chunk_index : sha256(chunk.content)) —
    never row ids (they change on reprocess). Same inputs → same
    fingerprint → the existing embedding is reused; any content change
    produces a different fingerprint → the vector is regenerated.
    """
    content_hash = hashlib.sha256(chunk_content.encode("utf-8")).hexdigest()
    basis = f"{document_content_hash}:{chunk_index}:{content_hash}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


@dataclass
class IndexingStats:
    """Outcome of one explicit index run (safe to print/log)."""

    eligible_chunks: int = 0
    pending_chunks: int = 0
    embedded_chunks: int = 0
    up_to_date_chunks: int = 0
    batches: int = 0
    dry_run: bool = False


class IndexingService:
    def __init__(
        self,
        db: Session,
        provider: EmbeddingProvider | None = None,
    ) -> None:
        self.db = db
        self.settings = get_settings()
        self.provider = provider if provider is not None else get_embedding_provider(self.settings)

    def index_all(self, *, force: bool = False, dry_run: bool = False) -> IndexingStats:
        """Embed every eligible chunk that is missing, stale, or from an
        older model. `force=True` re-embeds everything eligible."""
        ensure_configured_dimensions(self.settings, self.provider)
        stats = IndexingStats(dry_run=dry_run)

        rows = self.db.execute(
            select(DocumentChunk, Document.content_hash.label("document_content_hash"))
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(
                Document.status == "READY",
                Document.knowledge_status.in_(INDEXABLE_KNOWLEDGE_STATUSES),
                Document.content_hash.is_not(None),
            )
            .order_by(Document.id, DocumentChunk.chunk_index)
        ).all()

        pending: list[tuple[DocumentChunk, str]] = []
        for chunk, document_content_hash in rows:
            fingerprint = chunk_fingerprint(
                document_content_hash, chunk.chunk_index, chunk.content
            )
            up_to_date = (
                chunk.embedding is not None
                and chunk.embedding_model == self.provider.model_name
                and chunk.embedding_fingerprint == fingerprint
            )
            if up_to_date and not force:
                stats.up_to_date_chunks += 1
            else:
                pending.append((chunk, fingerprint))

        stats.eligible_chunks = len(rows)
        stats.pending_chunks = len(pending)
        logger.info(
            "index_run_started model=%s eligible=%d pending=%d up_to_date=%d "
            "force=%s dry_run=%s",
            self.provider.model_name,
            stats.eligible_chunks,
            stats.pending_chunks,
            stats.up_to_date_chunks,
            force,
            dry_run,
        )

        if dry_run or not pending:
            if dry_run:
                logger.info("index_run_dry_run pending=%d (no embeddings requested)", len(pending))
            else:
                logger.info("index_run_completed embedded=0 up_to_date=%d", stats.up_to_date_chunks)
            return stats

        batch_size = self.settings.embedding_batch_size
        passage_prefix = self.settings.embedding_passage_prefix
        for start in range(0, len(pending), batch_size):
            batch = pending[start : start + batch_size]
            texts = [passage_prefix + chunk.content for chunk, _ in batch]
            try:
                vectors = self.provider.embed_batch(texts)
            except Exception as exc:
                # Nothing in this batch is committed: the chunks keep their
                # old/NULL embeddings and therefore stay un-searchable.
                self.db.rollback()
                logger.error(
                    "index_batch_failed model=%s batch_start=%d batch_size=%d "
                    "error_type=%s (affected chunks remain un-searchable)",
                    self.provider.model_name,
                    start,
                    len(batch),
                    type(exc).__name__,
                )
                raise
            embedded_at = datetime.now(timezone.utc)
            for (chunk, fingerprint), vector in zip(batch, vectors):
                chunk.embedding = vector
                chunk.embedding_model = self.provider.model_name
                chunk.embedding_fingerprint = fingerprint
                chunk.embedded_at = embedded_at
            self.db.commit()
            stats.embedded_chunks += len(batch)
            stats.batches += 1
            logger.info(
                "index_batch_embedded model=%s batch_start=%d count=%d",
                self.provider.model_name,
                start,
                len(batch),
            )

        logger.info(
            "index_run_completed model=%s embedded=%d up_to_date=%d",
            self.provider.model_name,
            stats.embedded_chunks,
            stats.up_to_date_chunks,
        )
        return stats
