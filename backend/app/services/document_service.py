"""Document service — owns the knowledge ingestion lifecycle (Phase 6).

State machine (clients can NEVER set status themselves):

    PENDING ──► PROCESSING ──► READY     (pipeline succeeded)
        │             │
        │             └──────► FAILED    (safe reason stored on the row)

Synchronous by design: documents are small Markdown/text files bounded
by MAX_DOCUMENT_BYTES, the pipeline runs in milliseconds, and a sync
call keeps status transitions and error handling honest. No Celery/
Redis/worker system — there is no real need for it at this scale.
"""

from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.core.exceptions import (
    ConflictError,
    InvalidInputError,
    NotFoundError,
    ProcessingError,
)
from app.core.logging import get_logger
from app.ingestion.extractors import (
    IngestionError,
    infer_source_type,
    storage_failure_reason,
)
from app.ingestion.pipeline import content_hash, normalize, run_pipeline
from app.repositories.document_repository import DocumentRepository
from app.schemas.document import (
    ChunkOut,
    DocumentCreate,
    DocumentDetailOut,
    DocumentOut,
)

logger = get_logger("app.documents")

# When no filename hint exists, new uploads default to Markdown.
DEFAULT_SOURCE_TYPE = "markdown"
SUPPORTED_TYPES_HELP = "Supported types: Markdown (.md) and plain text (.txt)."


def _chunk_out(chunk) -> ChunkOut:
    return ChunkOut(
        id=chunk.id,
        chunk_index=chunk.chunk_index,
        section_id=chunk.section_id,
        section_title=chunk.section_title,
        content=chunk.content,
        char_count=chunk.char_count,
        pipeline_version=chunk.pipeline_version,
        created_at=chunk.created_at,
    )


def _detail(document, chunks) -> DocumentDetailOut:
    return DocumentDetailOut(
        id=document.id,
        title=document.title,
        source=document.source,
        source_type=document.source_type,
        knowledge_status=document.knowledge_status,
        status=document.status,
        failure_reason=document.failure_reason,
        content_hash=document.content_hash,
        chunk_count=len(chunks),
        processed_at=document.processed_at,
        created_at=document.created_at,
        updated_at=document.updated_at,
        content=document.content or "",
        chunks=[_chunk_out(chunk) for chunk in chunks],
    )


def _summary(document, chunk_count: int) -> DocumentOut:
    return DocumentOut(
        id=document.id,
        title=document.title,
        source=document.source,
        source_type=document.source_type,
        knowledge_status=document.knowledge_status,
        status=document.status,
        failure_reason=document.failure_reason,
        content_hash=document.content_hash,
        chunk_count=chunk_count,
        processed_at=document.processed_at,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


class DocumentService:
    def __init__(self, db):
        self.repo = DocumentRepository(db)

    # --- reads -----------------------------------------------------------

    def list_documents(self) -> list[DocumentOut]:
        return [
            _summary(document, chunk_count)
            for document, chunk_count in self.repo.list_documents()
        ]

    def get_document(self, document_id: str) -> DocumentDetailOut:
        document = self.repo.get_with_chunks(document_id)
        if document is None:
            raise NotFoundError("Document not found.")
        return _detail(document, document.chunks)

    # --- ingestion -------------------------------------------------------

    @staticmethod
    def _validate_content(raw: str) -> tuple[str, str]:
        """Request-level validation. Returns (normalized, content_hash).

        Runs BEFORE any row exists — invalid input never creates a
        document. The byte limit is checked on the UTF-8 encoding.
        """
        settings = get_settings()
        if not raw.strip():
            raise InvalidInputError("The document contains no meaningful text.")
        byte_length = len(raw.encode("utf-8"))
        if byte_length > settings.max_document_bytes:
            raise InvalidInputError(
                f"The document exceeds the {settings.max_document_bytes} byte limit."
            )
        normalized = normalize(raw)
        if not normalized:
            raise InvalidInputError("The document contains no meaningful text.")
        return normalized, content_hash(normalized)

    @staticmethod
    def _resolve_source_type(payload: DocumentCreate) -> str:
        if payload.source_type:
            return payload.source_type
        inferred = infer_source_type(payload.source)
        if inferred:
            return inferred
        if payload.source:
            # A filename that claims an unsupported type is rejected —
            # the extension hint is honored, never silently ignored.
            raise InvalidInputError(f"Unsupported document type. {SUPPORTED_TYPES_HELP}")
        return DEFAULT_SOURCE_TYPE

    def create_document(
        self, payload: DocumentCreate, document_id: str | None = None
    ) -> DocumentDetailOut:
        source_type = self._resolve_source_type(payload)
        _, doc_hash = self._validate_content(payload.content)

        existing = self.repo.find_by_content_hash(doc_hash)
        if existing is not None:
            raise ConflictError(
                "An identical document has already been ingested.",
                details={
                    "documentId": existing.id,
                    "title": existing.title,
                    "status": existing.status,
                },
            )

        # PostgreSQL text columns cannot store NUL (0x00) bytes, so a
        # NUL-byte upload is intercepted BEFORE the INSERT (SQLite used
        # to tolerate it and fail later in the pipeline). Same safe
        # reason, same FAILED-document contract — the stored content is
        # NUL-stripped because the database cannot represent binary data
        # as text; reprocessing still fails the extractor sniff, so the
        # document can never become READY.
        binary_reason = storage_failure_reason(payload.content)
        if binary_reason is not None:
            document = self.repo.create_document_row(
                document_id=document_id,
                title=payload.title,
                source=payload.source,
                source_type=source_type,
                knowledge_status=payload.knowledge_status or "approved",
                content=payload.content.replace("\x00", ""),
                content_hash=doc_hash,
            )
            self.repo.mark_failed(document, binary_reason)
            logger.warning(
                "document_processing_failed document_id=%s reason=%s",
                document.id,
                binary_reason,
            )
            raise ProcessingError(
                "The document could not be processed.",
                details={
                    "documentId": document.id,
                    "status": "FAILED",
                    "reason": binary_reason,
                },
            ) from None

        try:
            document = self.repo.create_document_row(
                document_id=document_id,
                title=payload.title,
                source=payload.source,
                source_type=source_type,
                knowledge_status=payload.knowledge_status or "approved",
                content=payload.content,
                content_hash=doc_hash,
            )
        except IntegrityError:
            # Concurrent identical upload won the unique-hash race.
            self.repo.db.rollback()
            existing = self.repo.find_by_content_hash(doc_hash)
            if existing is None:
                raise
            raise ConflictError(
                "An identical document has already been ingested.",
                details={
                    "documentId": existing.id,
                    "title": existing.title,
                    "status": existing.status,
                },
            )

        logger.info(
            "document_upload_received document_id=%s source_type=%s bytes=%d",
            document.id,
            source_type,
            len(payload.content.encode("utf-8")),
        )
        return self._process(document)

    def ingest_content(
        self,
        document,
        *,
        content: str,
        source_type: str,
        source: str | None = None,
        knowledge_status: str | None = None,
    ) -> DocumentDetailOut:
        """Seed path: fill a legacy row (no stored content) and process it."""
        _, doc_hash = self._validate_content(content)
        document.content = content
        document.source_type = source_type
        document.content_hash = doc_hash
        if knowledge_status is not None:
            document.knowledge_status = knowledge_status
        if source is not None:
            document.source = source
        self.repo.db.commit()
        return self._process(document)

    def reprocess(self, document_id: str) -> DocumentDetailOut:
        """Re-run the pipeline over stored content, replacing old chunks."""
        document = self.repo.get_with_chunks(document_id)
        if document is None:
            raise NotFoundError("Document not found.")
        if not document.content:
            raise InvalidInputError(
                "This document has no stored content to reprocess."
            )
        logger.info(
            "document_reprocess_requested document_id=%s existing_chunks=%d",
            document.id,
            len(document.chunks),
        )
        return self._process(document)

    # --- state transitions ----------------------------------------------

    def _process(self, document) -> DocumentDetailOut:
        """PENDING/PROCESSING → READY | FAILED. Never partial, never optimistic."""
        self.repo.begin_processing(document)
        logger.info(
            "document_processing_started document_id=%s source_type=%s",
            document.id,
            document.source_type,
        )

        try:
            processed = run_pipeline(
                document.content or "", document.source_type, document.title
            )
        except IngestionError as exc:
            self.repo.mark_failed(document, exc.reason)
            logger.warning(
                "document_processing_failed document_id=%s reason=%s",
                document.id,
                exc.reason,
            )
            raise ProcessingError(
                "The document could not be processed.",
                details={
                    "documentId": document.id,
                    "status": "FAILED",
                    "reason": exc.reason,
                },
            ) from None

        # The document's own H1 is authoritative for Markdown uploads
        # (extract_title falls back to the existing title for plain text).
        document.title = processed.title
        chunks = self.repo.finalize_ready(document, processed.chunks)
        logger.info(
            "document_ready document_id=%s sections=%d chunks=%d hash=%s",
            document.id,
            len(processed.sections),
            len(chunks),
            processed.content_hash[:12],
        )
        return _detail(document, chunks)
