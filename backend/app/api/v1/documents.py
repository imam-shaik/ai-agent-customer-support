"""Document endpoints — the knowledge ingestion boundary (Phase 6).

The pipeline owns processing status: clients can create documents, read
their honest status, and trigger a reprocess — but can never set a
status field themselves.
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.document import DocumentCreate, DocumentDetailOut, DocumentOut
from app.services.document_service import DocumentService

router = APIRouter(tags=["documents"])


@router.get(
    "/documents",
    response_model=list[DocumentOut],
    status_code=status.HTTP_200_OK,
)
def list_documents(db: Session = Depends(get_db)) -> list[DocumentOut]:
    """All documents with honest processing status and chunk counts."""
    return DocumentService(db).list_documents()


@router.get(
    "/documents/{document_id}",
    response_model=DocumentDetailOut,
    status_code=status.HTTP_200_OK,
)
def get_document(document_id: str, db: Session = Depends(get_db)) -> DocumentDetailOut:
    """Document detail: stored content, failure reason, and every chunk
    with its section provenance (chunk_index, section_id, section_title).

    404 — unknown document.
    """
    return DocumentService(db).get_document(document_id)


@router.post(
    "/documents",
    response_model=DocumentDetailOut,
    status_code=status.HTTP_201_CREATED,
)
def create_document(
    payload: DocumentCreate, db: Session = Depends(get_db)
) -> DocumentDetailOut:
    """Ingest a document synchronously: validate → extract → normalize →
    section detection → chunking → READY.

    Response is the processed document (status READY with chunks).
    Errors: 422 unsupported/empty/oversized content, 409 identical
    content already ingested (details.documentId), 422 PROCESSING_FAILED
    when extraction fails (the row is persisted as FAILED, never READY).
    """
    return DocumentService(db).create_document(payload)


@router.post(
    "/documents/{document_id}/reprocess",
    response_model=DocumentDetailOut,
    status_code=status.HTTP_200_OK,
)
def reprocess_document(
    document_id: str, db: Session = Depends(get_db)
) -> DocumentDetailOut:
    """Re-run the pipeline over the stored content, replacing the
    document's chunks atomically. Historical citations are preserved
    (their chunk link is nulled, their evidence snapshot untouched).

    404 — unknown document. 422 — no stored content, or processing failed.
    """
    return DocumentService(db).reprocess(document_id)
