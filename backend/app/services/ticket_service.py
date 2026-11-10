"""Escalation ticket service: creation rules, listing, status changes."""

import random
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError

from app.core.exceptions import ConflictError, NotFoundError
from app.core.logging import get_logger
from app.models import Ticket
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.ticket_repository import TicketRepository
from app.schemas.chat import MessageOut
from app.schemas.ticket import (
    ConversationTicketListOut,
    ConversationTicketOut,
    EscalationCreate,
    TicketDetailOut,
    TicketEventOut,
    TicketListOut,
    TicketSummaryOut,
    TicketStatusUpdate,
)
from app.services.chat_service import _message_out
logger = get_logger("app.tickets")

_ALLOWED_STATUSES = ("OPEN", "IN_PROGRESS", "RESOLVED")


def _summary(ticket: Ticket) -> TicketSummaryOut:
    return TicketSummaryOut(
        id=ticket.id,
        conversation_id=ticket.conversation_id,
        customer_name=ticket.customer_name,
        customer_email=ticket.customer_email,
        customer_phone=ticket.customer_phone,
        summary=ticket.summary,
        escalation_reason=ticket.escalation_reason,
        status=ticket.status,
        priority=ticket.priority,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
    )


class TicketService:
    def __init__(self, db):
        self.repo = TicketRepository(db)
        self.conversations = ConversationRepository(db)

    @staticmethod
    def _generate_id() -> str:
        return f"NSD-{datetime.now(timezone.utc).year}-{random.randint(1000, 9999)}"

    def create_escalation(
        self, conversation_id: str, payload: EscalationCreate
    ) -> TicketDetailOut:
        if self.conversations.get_conversation(conversation_id) is None:
            raise NotFoundError("Conversation not found.")

        # Duplicate protection: one unresolved ticket per conversation, so
        # a double-click or retry cannot create a second ticket.
        existing = self.repo.find_active_ticket_for_conversation(conversation_id)
        if existing is not None:
            raise ConflictError(
                "This conversation already has an open escalation.",
                details={"ticketId": existing.id, "status": existing.status},
            )

        if not self.conversations.conversation_has_messages(conversation_id):
            raise ConflictError(
                "Cannot escalate an empty conversation — context is required."
            )

        # The ticket and its creation event are one transaction: a ticket
        # must never exist without the audit event that explains it.
        ticket: Ticket | None = None
        for attempt in range(2):
            ticket = Ticket(
                id=self._generate_id(),
                conversation_id=conversation_id,
                customer_name=payload.customer_name,
                customer_email=payload.customer_email,
                customer_phone=(
                    payload.customer_phone.strip()
                    if payload.customer_phone
                    else None
                ),
                summary=payload.summary,
                original_question=payload.original_question,
                escalation_reason=payload.escalation_reason,
                status="OPEN",
                priority=payload.priority,
            )
            try:
                self.repo.add_ticket_pending(ticket)
                self.repo.db.flush()
                self.repo.add_ticket_event_pending(
                    ticket.id,
                    "ticket_created",
                    new_value="OPEN",
                    actor="customer_workflow",
                )
                self.repo.db.commit()
                break
            except IntegrityError:
                # Primary-key collision on the human-readable id — retry once.
                self.repo.db.rollback()
                if attempt == 1:
                    raise

        assert ticket is not None  # the loop either breaks or raises
        logger.info(
            "ticket_created ticket_id=%s conversation_id=%s",
            ticket.id,
            conversation_id,
        )
        return self.get_detail(ticket.id)

    def list_tickets(
        self, *, status: str | None, query: str | None, limit: int, offset: int
    ) -> TicketListOut:
        rows, total = self.repo.list_tickets(
            status=status, query=query, limit=limit, offset=offset
        )
        return TicketListOut(
            items=[_summary(ticket) for ticket in rows],
            total=total,
            limit=limit,
            offset=offset,
            counts=self.repo.count_tickets_by_status(query=query),
        )

    def list_conversation_tickets(self, conversation_id: str) -> ConversationTicketListOut:
        """Every ticket raised from one conversation, newest first.

        Customer-facing view: id, status, summary and timestamps only — no
        staff internals. Unknown conversations 404 like the transcript read.
        """
        if self.conversations.get_conversation(conversation_id) is None:
            raise NotFoundError("Conversation not found.")

        rows = self.repo.list_tickets_for_conversation(conversation_id)
        return ConversationTicketListOut(
            conversation_id=conversation_id,
            total=len(rows),
            items=[
                ConversationTicketOut(
                    id=ticket.id,
                    status=ticket.status,
                    summary=ticket.summary,
                    created_at=ticket.created_at,
                    updated_at=ticket.updated_at,
                )
                for ticket in rows
            ],
        )

    def get_detail(self, ticket_id: str) -> TicketDetailOut:
        ticket = self.repo.get_ticket_with_context(ticket_id)
        if ticket is None:
            raise NotFoundError("Ticket not found.")

        messages: list[MessageOut] = []
        if ticket.conversation is not None:
            for message in ticket.conversation.messages:
                messages.append(_message_out(message, list(message.citations)))

        events = [
            TicketEventOut(
                id=event.id,
                event_type=event.event_type,
                old_value=event.old_value,
                new_value=event.new_value,
                actor=event.actor,
                created_at=event.created_at,
            )
            for event in ticket.events
        ]

        base = _summary(ticket)
        return TicketDetailOut(
            **base.model_dump(),
            original_question=ticket.original_question,
            messages=messages,
            events=events,
        )

    def update_status(self, ticket_id: str, payload: TicketStatusUpdate) -> TicketDetailOut:
        # Lock the row: the status change and its audit event must commit
        # together, and concurrent staff updates must not interleave.
        ticket = self.repo.get_ticket_for_update(ticket_id)
        if ticket is None:
            raise NotFoundError("Ticket not found.")
        if payload.status not in _ALLOWED_STATUSES:  # defense in depth (schema also checks)
            raise ConflictError("Unsupported ticket status.", details={"status": payload.status})

        old_status = ticket.status
        expected = payload.expected_status
        if expected is not None and old_status != expected:
            # If the ticket already reached the requested state, this is a
            # harmless duplicate (e.g. two tabs clicked the same target).
            if old_status == payload.status:
                return self.get_detail(ticket.id)
            raise ConflictError(
                "Ticket status changed since it was loaded.",
                details={
                    "ticketId": ticket.id,
                    "currentStatus": old_status,
                    "updatedAt": ticket.updated_at.isoformat()
                    if ticket.updated_at
                    else None,
                },
            )

        if old_status != payload.status:
            try:
                ticket.status = payload.status
                ticket.updated_at = datetime.now(timezone.utc)
                self.repo.add_ticket_event_pending(
                    ticket.id,
                    "status_changed",
                    old_value=old_status,
                    new_value=payload.status,
                    actor=payload.actor,
                )
                # ONE commit for the status + event. If either fails, the
                # audit trail and the ticket state cannot diverge.
                self.repo.db.commit()
            except Exception:
                self.repo.db.rollback()
                raise
            logger.info(
                "ticket_status_changed ticket_id=%s old=%s new=%s actor=%s",
                ticket.id,
                old_status,
                payload.status,
                payload.actor,
            )
        return self.get_detail(ticket.id)
