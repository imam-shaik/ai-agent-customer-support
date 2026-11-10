"""Retrieval service (Phase 7 §9–11).

RETRIEVAL FINDS POSSIBLE EVIDENCE. It returns structured candidates and
never generates text, never claims the evidence is sufficient to answer
(Phase 8 decides that), and never escalates anything.

Flow:
    validate query → embed query (only embedding during search) →
    SQL with the knowledge_status scope filter applied INSIDE the query →
    cosine ranking → structured candidates

Scope safety (§11): the WHERE clause carries Document.knowledge_status —
normal retrieval allows only 'approved'; 'challenge_fixture' rows are
reachable exclusively via the explicit include_challenge_fixtures option
(caller-side: tests and CLI only — the HTTP schema forbids the field);
'archived' is never reachable at all.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import InvalidInputError
from app.core.logging import get_logger
from app.embeddings import (
    EmbeddingProvider,
    EmbeddingProviderError,
    ensure_configured_dimensions,
    get_embedding_provider,
)
from app.models.entities import Document, DocumentChunk
from app.services.provider_mode_service import is_demo_mode

logger = get_logger("app.retrieval")

# Scope rule values — enforced in SQL, never filtered after the fact.
NORMAL_RETRIEVAL_STATUSES = ("approved",)
CHALLENGE_RETRIEVAL_STATUSES = ("approved", "challenge_fixture")


@dataclass(frozen=True)
class RetrievalCandidate:
    """One possible-evidence chunk — NOT an answer."""

    chunk_id: str
    document_id: str
    document_title: str
    section_id: str
    section_title: str
    chunk_index: int
    content: str
    knowledge_status: str
    source: str | None
    cosine_distance: float
    # Exact identity: cosine_similarity = 1 - cosine_distance (pgvector's
    # <=> is 1 - cos(a,b)). No squashing, no invented "score" semantics.
    cosine_similarity: float


@dataclass(frozen=True)
class RetrievalResult:
    embedding_model: str
    limit: int
    include_challenge_fixtures: bool
    min_cosine_similarity: float
    candidates: tuple[RetrievalCandidate, ...]


class RetrievalService:
    def __init__(
        self,
        db: Session,
        provider: EmbeddingProvider | None = None,
    ) -> None:
        self.db = db
        self.settings = get_settings()
        # The default provider is resolved INSIDE retrieve(), after payload
        # validation: an invalid query must get its 422 regardless of
        # whether embedding credentials are configured (a valid query with
        # no credentials still gets the explicit 503).
        self._provider = provider

    def retrieve(
        self,
        *,
        query: str,
        limit: int | None = None,
        include_challenge_fixtures: bool = False,
        min_cosine_similarity: float | None = None,
    ) -> RetrievalResult:
        settings = self.settings

        # --- validation (explicit config, no magic numbers) ---
        cleaned = (query or "").strip()
        if not cleaned:
            raise InvalidInputError("query must not be empty.")
        if len(cleaned) > settings.retrieval_max_query_chars:
            raise InvalidInputError(
                f"query must be at most {settings.retrieval_max_query_chars} characters."
            )
        resolved_limit = settings.retrieval_top_k_default if limit is None else limit
        if not 1 <= resolved_limit <= settings.retrieval_top_k_max:
            raise InvalidInputError(
                f"limit must be within [1, {settings.retrieval_top_k_max}]."
            )
        threshold = (
            settings.retrieval_min_cosine_similarity
            if min_cosine_similarity is None
            else min_cosine_similarity
        )

        # --- explicit local Demo mode: lexical retrieval over the SAME
        # stored chunks. It reads document content only, so it works with
        # no API key and never writes to the live embedding columns.
        if is_demo_mode():
            return self._retrieve_demo(
                query=cleaned,
                limit=resolved_limit,
                include_challenge_fixtures=include_challenge_fixtures,
                threshold=threshold,
            )

        provider = self._provider if self._provider is not None else get_embedding_provider(settings)
        ensure_configured_dimensions(settings, provider)

        # Log shape only — never the full query text (§17).
        logger.info(
            "retrieval_query_received query_chars=%d limit=%d fixtures=%s",
            len(cleaned),
            resolved_limit,
            include_challenge_fixtures,
        )

        # --- embed the query (the ONLY embedding during a search) ---
        try:
            query_vector = provider.embed_text(settings.embedding_query_prefix + cleaned)
        except EmbeddingProviderError:
            logger.error(
                "retrieval_embedding_failed model=%s error_type=EmbeddingProviderError",
                provider.model_name,
            )
            raise

        # --- scope filter INSIDE the SQL query (§11) ---
        allowed_statuses = (
            CHALLENGE_RETRIEVAL_STATUSES
            if include_challenge_fixtures
            else NORMAL_RETRIEVAL_STATUSES
        )
        distance = DocumentChunk.embedding.cosine_distance(query_vector)
        stmt = (
            select(
                DocumentChunk,
                Document.title.label("document_title"),
                Document.source.label("document_source"),
                Document.knowledge_status.label("document_knowledge_status"),
                distance.label("cosine_distance"),
            )
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(
                Document.status == "READY",
                # ← the knowledge_status boundary, enforced by the database
                Document.knowledge_status.in_(allowed_statuses),
                DocumentChunk.embedding.is_not(None),
                # Old-model vectors are never searched (model change →
                # they are stale until the explicit re-index run).
                DocumentChunk.embedding_model == provider.model_name,
                (1.0 - distance) >= threshold,
            )
            .order_by(distance)
            .limit(resolved_limit)
        )

        rows = self.db.execute(stmt).all()
        candidates = tuple(
            RetrievalCandidate(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                document_title=document_title,
                section_id=chunk.section_id,
                section_title=chunk.section_title,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                knowledge_status=knowledge_status,
                source=document_source,
                cosine_distance=float(cosine_distance),
                cosine_similarity=1.0 - float(cosine_distance),
            )
            for chunk, document_title, document_source, knowledge_status, cosine_distance in rows
        )

        logger.info(
            "retrieval_query_completed candidates=%d limit=%d",
            len(candidates),
            resolved_limit,
        )
        return RetrievalResult(
            embedding_model=provider.model_name,
            limit=resolved_limit,
            include_challenge_fixtures=include_challenge_fixtures,
            min_cosine_similarity=threshold,
            candidates=candidates,
        )

    def _retrieve_demo(
        self,
        *,
        query: str,
        limit: int,
        include_challenge_fixtures: bool,
        threshold: float,
    ) -> RetrievalResult:
        """Deterministic Demo-mode retrieval (no network, no key).

        The fake lexical embedding is computed over stored chunk content
        at query time, so it is independent of whatever live vectors are
        in pgvector. Only READY + in-scope documents are visible, with
        the same SQL scope boundary as live retrieval.
        """
        from app.embeddings.fake import FakeEmbeddingProvider

        provider = FakeEmbeddingProvider(dimensions=self.settings.embedding_dimensions)
        allowed_statuses = (
            CHALLENGE_RETRIEVAL_STATUSES
            if include_challenge_fixtures
            else NORMAL_RETRIEVAL_STATUSES
        )
        rows = self.db.execute(
            select(
                DocumentChunk,
                Document.title.label("document_title"),
                Document.source.label("document_source"),
                Document.knowledge_status.label("document_knowledge_status"),
            )
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(
                Document.status == "READY",
                Document.knowledge_status.in_(allowed_statuses),
            )
            .order_by(Document.id, DocumentChunk.chunk_index)
        ).all()

        query_vector = provider.embed_text(query)
        ranked: list[tuple[float, DocumentChunk, str, str | None, str]] = []
        for chunk, document_title, document_source, knowledge_status in rows:
            chunk_vector = provider.embed_text(chunk.content)
            similarity = sum(a * b for a, b in zip(query_vector, chunk_vector))
            if similarity < threshold:
                continue
            ranked.append(
                (similarity, chunk, document_title, document_source, knowledge_status)
            )
        ranked.sort(key=lambda item: item[0], reverse=True)

        candidates = tuple(
            RetrievalCandidate(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                document_title=document_title,
                section_id=chunk.section_id,
                section_title=chunk.section_title,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                knowledge_status=knowledge_status,
                source=document_source,
                cosine_distance=1.0 - similarity,
                cosine_similarity=similarity,
            )
            for similarity, chunk, document_title, document_source, knowledge_status in ranked[
                :limit
            ]
        )

        logger.info(
            "retrieval_query_completed mode=demo candidates=%d limit=%d",
            len(candidates),
            limit,
        )
        return RetrievalResult(
            embedding_model=provider.model_name,
            limit=limit,
            include_challenge_fixtures=include_challenge_fixtures,
            min_cosine_similarity=threshold,
            candidates=candidates,
        )
