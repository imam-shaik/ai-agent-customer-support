"""Repository-level behavior (below the service layer)."""


def test_conversation_repository_roundtrip(db_session):
    from app.repositories.conversation_repository import ConversationRepository

    repo = ConversationRepository(db_session)
    conversation = repo.create_conversation()
    assert repo.get_conversation(conversation.id) is not None

    message = repo.add_message(conversation.id, role="user", content="hello")
    assert message.conversation_id == conversation.id
    assert repo.conversation_has_messages(conversation.id) is True
    assert len(repo.list_conversation_messages(conversation.id)) == 1


def test_ticket_repository_filters_and_finds_active(db_session, conversation_with_message):
    from app.models import Ticket
    from app.repositories.ticket_repository import TicketRepository

    conversation_id = conversation_with_message["conversationId"]
    repo = TicketRepository(db_session)
    ticket = Ticket(
        id="NSD-2026-7777",
        conversation_id=conversation_id,
        customer_name="Test User",
        customer_email="test@example.com",
        summary="Test summary",
        original_question="Test question",
        escalation_reason="Test reason",
        status="OPEN",
        priority="high",
    )
    repo.create_ticket(ticket)

    found = repo.find_active_ticket_for_conversation(conversation_id)
    assert found is not None and found.id == "NSD-2026-7777"

    rows, total = repo.list_tickets(status="OPEN")
    assert any(row.id == "NSD-2026-7777" for row in rows)
    assert total >= len(rows)

    rows, _ = repo.list_tickets(query="7777")
    assert [row.id for row in rows] == ["NSD-2026-7777"]


def test_document_repository_state_machine(db_session):
    """PENDING → PROCESSING → READY|FAILED, with chunk replacement."""
    from app.ingestion.pipeline import ChunkDraft
    from app.repositories.document_repository import DocumentRepository

    repo = DocumentRepository(db_session)
    document = repo.create_document_row(
        document_id=None,
        title="Retention Policy",
        source="knowledge/retention",
        source_type="markdown",
        knowledge_status="approved",
        content="# Retention Policy\n\n30 days.",
        content_hash="a" * 64,
    )
    assert document.status == "PENDING"

    repo.begin_processing(document)
    assert document.status == "PROCESSING"

    chunks = repo.finalize_ready(
        document,
        [ChunkDraft(chunk_index=0, section_id="main", section_title="Retention Policy", content="30 days.")],
    )
    assert document.status == "READY"
    assert document.failure_reason is None
    assert [chunk.chunk_index for chunk in chunks] == [0]
    assert repo.get_with_chunks(document.id) is not None

    repo.mark_failed(document, "The document could not be read.")
    assert document.status == "FAILED"
    assert document.failure_reason == "The document could not be read."
    assert document.processed_at is not None


def test_finalize_ready_preserves_historical_citations(db_session):
    """Reprocessing nulls chunk links but never deletes the citation."""
    from app.ingestion.pipeline import ChunkDraft
    from app.models import Citation, DocumentChunk
    from app.repositories.conversation_repository import ConversationRepository
    from app.repositories.document_repository import DocumentRepository
    from app.schemas.document import DocumentCreate
    from app.services.document_service import DocumentService

    conversation_repo = ConversationRepository(db_session)
    conversation = conversation_repo.create_conversation()
    message = conversation_repo.add_message(
        conversation.id, role="assistant", content="Answer with citation."
    )

    service = DocumentService(db_session)
    created = service.create_document(
        DocumentCreate(
            title="Citation Fixture",
            content="# Citation Fixture\n\n## One\n\nAlpha paragraph.\n\n## Two\n\nBeta paragraph.",
            source_type="markdown",
        )
    )
    repo = DocumentRepository(db_session)
    document = repo.get_with_chunks(created.id)
    first_chunk = document.chunks[0]
    snapshot = {
        "documentTitle": document.title,
        "sectionTitle": first_chunk.section_title,
        "snippet": first_chunk.content[:80],
    }
    citation = Citation(
        message_id=message.id,
        document_id=document.id,
        section_ref=first_chunk.section_id,
        chunk_id=first_chunk.id,
        evidence_snapshot=snapshot,
    )
    db_session.add(citation)
    db_session.commit()

    old_chunk_id = first_chunk.id
    old_section_ids = [c.section_id for c in document.chunks]
    drafts = [
        ChunkDraft(chunk_index=i, section_id=sid, section_title="Title", content=f"chunk {i}")
        for i, sid in enumerate(old_section_ids)
    ]
    repo.finalize_ready(document, drafts)
    db_session.expire_all()

    # New chunks replaced the old rows (never orphaned, never reused).
    assert db_session.get(DocumentChunk, old_chunk_id) is None
    replacement = repo.get_with_chunks(document.id)
    assert old_chunk_id not in {chunk.id for chunk in replacement.chunks}

    # The historical citation survived with its evidence snapshot intact.
    citation_row = db_session.get(Citation, citation.id)
    assert citation_row is not None
    assert citation_row.chunk_id is None
    assert citation_row.evidence_snapshot == snapshot
