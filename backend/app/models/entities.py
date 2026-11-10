"""Domain entities.

Design notes (Phase 5 → Phase 6):
- Conversation history is append-only historical evidence: messages and
  citations are never regenerated or overwritten.
- Citations carry an evidence snapshot so staff can always inspect what
  supported an answer *at the time it was generated* — even after the
  knowledge base changes.
- Phase 6 adds the knowledge pipeline: Documents gain ingestion fields
  (source type, stored content, content hash, failure reason) and
  DocumentChunk rows carry provenance (order + section reference) for
  every piece of retrievable text. Reprocessing replaces a document's
  chunks; historical citations survive via ON DELETE SET NULL on
  chunk_id plus their own evidence snapshot.
- Embeddings (Phase 7): document_chunks gains native pgvector storage
  (vector(2048)) plus the identity metadata that keeps vectors honest -
  which model produced them and a content-derived fingerprint that never
  depends on row ids. Vectors are written ONLY by the explicit indexing
  workflow, never during search.
"""

import threading
import time
import uuid
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

# Native pgvector dimension, fixed by the selected embedding model
# (nemotron-3-embed-1b → 2048). The original model (NV-EmbedQA-E5-v5, 1024)
# reached end-of-life on NVIDIA's API (HTTP 410, verified 2026-11-10), so
# the schema migrated vector(1024) → vector(2048) with all vectors cleared
# for re-embedding (migration c4f8a1d6e2b9). A different-dimension model
# requires a NEW migration, never a silent mismatch.
VECTOR_DIMENSIONS = 2048


def _uuid() -> str:
    return uuid.uuid4().hex


# Monotonic-timestamp state (see _now): the last emitted microsecond and
# the lock guarding it, so concurrent request threads can never emit two
# equal or out-of-order timestamps.
_stamp_lock = threading.Lock()
_last_stamp_us = 0


def _now() -> datetime:
    """Current UTC time, guaranteed STRICTLY INCREASING across calls.

    Windows clocks (Python <= 3.12) tick at ~15.6 ms, so two rows written
    within one turn — the customer message and its assistant reply — can
    otherwise carry the SAME timestamp. Every transcript is ordered by
    created_at (conversation relationship + repository queries), so a tie
    makes that order unstable: a reload can show the reply before the
    question. Bumping by 1 microsecond inside the same clock tick keeps
    the real chronology while making ordering deterministic everywhere —
    no schema change, and timestamps stay honest wall-clock times.
    """
    global _last_stamp_us
    with _stamp_lock:
        stamp_us = time.time_ns() // 1000
        if stamp_us <= _last_stamp_us:
            stamp_us = _last_stamp_us + 1
        _last_stamp_us = stamp_us
    return datetime.fromtimestamp(stamp_us / 1_000_000, tz=timezone.utc)


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING','PROCESSING','READY','FAILED')",
            name="ck_document_status",
        ),
        CheckConstraint(
            "source_type IN ('markdown','text')",
            name="ck_document_source_type",
        ),
        # DB-level guard for the retrieval gate (added in the Phase 7
        # Postgres migration — SQLite would have needed a table recreate).
        CheckConstraint(
            "knowledge_status IN ('approved','challenge_fixture','archived')",
            name="ck_document_knowledge_status",
        ),
        Index("ix_documents_content_hash", "content_hash", unique=True),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    source: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    # --- ingestion fields (Phase 6) ---
    source_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="markdown", server_default="markdown"
    )
    # Knowledge classification (post-approval decision): only "approved"
    # documents enter normal retrieval. "challenge_fixture" is the clearly
    # labeled conflicting-evidence material; "archived" is reserved for the
    # future knowledge-management UI. Enforced at the API boundary (Pydantic
    # Literal) AND by the ck_document_knowledge_status DB constraint.
    knowledge_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="approved", server_default="approved"
    )
    # Original uploaded text — kept so reprocessing never needs the file again.
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    # SHA-256 of the NORMALIZED text (see ingestion/pipeline.py) — duplicate
    # detection is by content, never by title.
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentChunk.chunk_index",
    )


class DocumentChunk(Base):
    """A retrievable piece of a document with full provenance.

    Chain: answer → citation → chunk → section → document.
    chunk_index is the deterministic global order within the document.
    """

    __tablename__ = "document_chunks"
    __table_args__ = (
        # No ANN index on `embedding`: pgvector's HNSW caps at 2000
        # dimensions and the live model (nemotron-3-embed-1b) emits 2048.
        # At MVP corpus scale pgvector's exact sequential cosine scan is
        # correct and fast, so search runs without an index. Revisit with a
        # halfvec expression index (or a <=2000-dim model) only if the
        # corpus grows enough to need approximate search.
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    document_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(nullable=False)
    section_id: Mapped[str] = mapped_column(String(200), nullable=False)
    section_title: Mapped[str] = mapped_column(String(300), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    char_count: Mapped[int] = mapped_column(nullable=False)
    # Which chunking rules produced this chunk (ingestion/pipeline.py).
    pipeline_version: Mapped[str] = mapped_column(
        String(10), nullable=False, default="1", server_default="1"
    )
    # --- embeddings (Phase 7) -------------------------------------------
    # Native pgvector column (never a JSON array). NULL = not indexed yet,
    # which keeps un-embedded chunks un-searchable instead of faking data.
    embedding: Mapped[list | None] = mapped_column(Vector(VECTOR_DIMENSIONS), nullable=True)
    # Which model produced the vector — retrieval filters on the currently
    # configured model, so old-model vectors are never treated as current.
    embedding_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Content-derived identity (NEVER row ids, which change on reprocess):
    # sha256(document.content_hash : chunk_index : sha256(chunk.content)).
    # A changed fingerprint invalidates the vector on the next index run.
    embedding_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    embedded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    document: Mapped[Document] = relationship(back_populates="chunks")


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="Message.created_at"
    )
    tickets: Mapped[list["Ticket"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint("role IN ('user','assistant','system')", name="ck_message_role"),
        # Phase 9 idempotency: one customer submission per request id per
        # conversation (partial index — legacy rows stay NULL).
        Index(
            "uq_messages_conversation_client_request",
            "conversation_id",
            "client_request_id",
            unique=True,
            postgresql_where=text("client_request_id IS NOT NULL"),
        ),
        # One assistant reply per customer turn, enforced by the database
        # even if two retries process concurrently.
        Index(
            "uq_messages_reply_to",
            "reply_to_message_id",
            unique=True,
            postgresql_where=text("reply_to_message_id IS NOT NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    conversation_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Justified structured payload: the agent's typed reply (kind + options
    # + checked docs), preserved verbatim so the exact answer that was
    # shown to the customer can be inspected later.
    reply: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Phase 9 idempotency: the customer-supplied stable request id (user
    # rows only) and the customer turn this assistant message answers.
    client_request_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    reply_to_message_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")
    citations: Mapped[list["Citation"]] = relationship(
        back_populates="message",
        cascade="all, delete-orphan",
        order_by="Citation.created_at",
    )
    feedback: Mapped["Feedback | None"] = relationship(
        back_populates="message", cascade="all, delete-orphan", uselist=False
    )


class Citation(Base):
    __tablename__ = "citations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    message_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("documents.id", ondelete="RESTRICT"), nullable=False
    )
    section_ref: Mapped[str] = mapped_column(String(200), nullable=False)
    # Future Phase 8 citations point at the exact chunk that was retrieved.
    # SET NULL (not CASCADE): reprocessing replaces chunks, but a historical
    # citation must survive — its evidence_snapshot keeps the answer-time text.
    chunk_id: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("document_chunks.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Snapshot of title/section/snippet at answer time — historical
    # inspection must not depend on the current knowledge base.
    evidence_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    message: Mapped[Message] = relationship(back_populates="citations")
    document: Mapped[Document] = relationship()


class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = (
        CheckConstraint(
            "status IN ('OPEN','IN_PROGRESS','RESOLVED')", name="ck_ticket_status"
        ),
        CheckConstraint("priority IN ('normal','high')", name="ck_ticket_priority"),
        Index("ix_tickets_conversation_status", "conversation_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # NSD-YYYY-NNNN
    conversation_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    customer_name: Mapped[str] = mapped_column(String(200), nullable=False)
    customer_email: Mapped[str] = mapped_column(String(320), nullable=False)
    # Optional contact channel: stored trimmed or NULL when not provided.
    customer_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    summary: Mapped[str] = mapped_column(String(300), nullable=False)
    original_question: Mapped[str] = mapped_column(Text, nullable=False)
    escalation_reason: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="OPEN")
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="normal")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    conversation: Mapped[Conversation] = relationship(back_populates="tickets")
    events: Mapped[list["TicketEvent"]] = relationship(
        back_populates="ticket", cascade="all, delete-orphan", order_by="TicketEvent.created_at"
    )


class TicketEvent(Base):
    __tablename__ = "ticket_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    ticket_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    old_value: Mapped[str | None] = mapped_column(String(100), nullable=True)
    new_value: Mapped[str | None] = mapped_column(String(100), nullable=True)
    actor: Mapped[str] = mapped_column(String(100), nullable=False, default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    ticket: Mapped[Ticket] = relationship(back_populates="events")


class Feedback(Base):
    __tablename__ = "feedback"
    __table_args__ = (
        CheckConstraint("rating IN ('helpful','not_helpful')", name="ck_feedback_rating"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    message_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    rating: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    message: Mapped[Message] = relationship(back_populates="feedback")


class StaffUser(Base):
    """A support-team member who can sign in to the staff workspace.

    The first account is created through the workspace's sign-up screen
    ("create the login first"); later sign-ins reuse it. Emails are
    normalized to lowercase and unique — the email is the login id.
    """

    __tablename__ = "staff_users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    # PBKDF2-SHA256 parameter string (see services/auth_service.py) —
    # never a raw or reversible password.
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    sessions: Mapped[list["StaffSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class StaffSession(Base):
    """One bearer-token sign-in session.

    Only the SHA-256 hash of the token is stored — a database leak can
    never reveal a usable bearer token, and logout simply deletes the
    row. Expiry is enforced at verification time (never trusted from the
    client); expired rows are deleted when encountered and pruned at
    sign-in.
    """

    __tablename__ = "staff_sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("staff_users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    user: Mapped[StaffUser] = relationship(back_populates="sessions")
