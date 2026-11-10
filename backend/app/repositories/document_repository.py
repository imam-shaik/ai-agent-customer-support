"""Document + chunk data access.

Owns the persistence side of the state machine: PENDING row creation,
PROCESSING transition, atomic READY finalization (chunks + status in one
commit), and FAILED with a safe reason. No business validation here.
"""

from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, selectinload

from app.ingestion.pipeline import ChunkDraft
from app.models import Citation, Document, DocumentChunk


class DocumentRepository:
    def __init__(self, db: Session):
        self.db = db

    # --- reads -----------------------------------------------------------

    def list_documents(self) -> list[tuple[Document, int]]:
        """All documents with their chunk counts (one query)."""
        rows = self.db.execute(
            select(Document, func.count(DocumentChunk.id).label("chunk_count"))
            .outerjoin(DocumentChunk, DocumentChunk.document_id == Document.id)
            .group_by(Document.id)
            .order_by(Document.created_at)
        ).all()
        return [(row[0], int(row[1])) for row in rows]

    def get_document(self, document_id: str) -> Document | None:
        return self.db.get(Document, document_id)

    def get_with_chunks(self, document_id: str) -> Document | None:
        return self.db.scalar(
            select(Document)
            .options(selectinload(Document.chunks))
            .where(Document.id == document_id)
        )

    def find_by_content_hash(self, content_hash: str) -> Document | None:
        return self.db.scalar(select(Document).where(Document.content_hash == content_hash))

    # --- state machine ---------------------------------------------------

    def create_document_row(
        self,
        *,
        document_id: str | None,
        title: str,
        source: str | None,
        source_type: str,
        knowledge_status: str,
        content: str,
        content_hash: str,
    ) -> Document:
        document = Document(
            title=title,
            source=source,
            source_type=source_type,
            knowledge_status=knowledge_status,
            content=content,
            content_hash=content_hash,
            status="PENDING",
        )
        if document_id is not None:
            document.id = document_id  # stable seed ids (frontend citation ids)
        self.db.add(document)
        self.db.commit()
        self.db.refresh(document)
        return document

    def begin_processing(self, document: Document) -> None:
        document.status = "PROCESSING"
        document.updated_at = datetime.now(timezone.utc)
        self.db.commit()

    def mark_failed(self, document: Document, reason: str) -> None:
        document.status = "FAILED"
        document.failure_reason = reason[:500]
        document.processed_at = datetime.now(timezone.utc)
        self.db.commit()

    def finalize_ready(self, document: Document, drafts: list[ChunkDraft]) -> list[DocumentChunk]:
        """Replace this document's chunks and mark READY in ONE commit.

        Old chunks are deleted (never orphaned) and any citation that
        pointed at them has its chunk_id nulled first — historical
        evidence survives reprocessing through its own snapshot.
        """
        stale_ids = [chunk.id for chunk in document.chunks]
        if stale_ids:
            self.db.execute(
                update(Citation)
                .where(Citation.chunk_id.in_(stale_ids))
                .values(chunk_id=None)
            )
        document.chunks.clear()  # delete-orphan: removes old chunk rows

        now = datetime.now(timezone.utc)
        for draft in drafts:
            document.chunks.append(
                DocumentChunk(
                    chunk_index=draft.chunk_index,
                    section_id=draft.section_id,
                    section_title=draft.section_title,
                    content=draft.content,
                    char_count=draft.char_count,
                )
            )
        document.status = "READY"
        document.failure_reason = None
        document.processed_at = now
        document.updated_at = now
        self.db.commit()
        self.db.refresh(document)
        return list(document.chunks)
