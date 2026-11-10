"""Document contracts (Phase 6 — ingestion).

Rules encoded here:
- There is NO way for a client to set processing status: the pipeline
  owns PENDING → PROCESSING → READY|FAILED (extra="forbid" rejects any
  attempt to send a status field).
- Responses expose honest processing information: status, failure
  reason, content hash, chunk count, and (in detail) the chunks
  themselves with their section provenance.
"""

from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.common import ApiModel

DocumentStatus = Literal["PENDING", "PROCESSING", "READY", "FAILED"]
SourceType = Literal["markdown", "text"]
# Knowledge classification (post-approval decision): only "approved" enters
# normal retrieval; "challenge_fixture" is the labeled conflicting-evidence
# material; "archived" is reserved for the future knowledge-management UI.
KnowledgeStatus = Literal["approved", "challenge_fixture", "archived"]


class DocumentCreate(ApiModel):
    title: str = Field(min_length=1, max_length=300)
    # Raw Markdown/text. The byte-size limit is enforced against the
    # configured MAX_DOCUMENT_BYTES in the service (unicode-aware).
    content: str = Field(min_length=1, max_length=2_000_000)
    source: str | None = Field(default=None, max_length=2000)
    # Optional hint; inferred from `source` extension when omitted.
    source_type: SourceType | None = None
    # Optional classification; defaults to "approved" (safe direction:
    # marking a document as non-approved only reduces retrieval scope).
    knowledge_status: KnowledgeStatus | None = None


class ChunkOut(ApiModel):
    id: str
    chunk_index: int
    section_id: str
    section_title: str
    content: str
    char_count: int
    pipeline_version: str
    created_at: datetime


class DocumentOut(ApiModel):
    id: str
    title: str
    source: str | None = None
    source_type: SourceType
    knowledge_status: KnowledgeStatus
    status: DocumentStatus
    failure_reason: str | None = None
    content_hash: str | None = None
    chunk_count: int = 0
    processed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class DocumentDetailOut(DocumentOut):
    content: str = ""
    chunks: list[ChunkOut] = []
