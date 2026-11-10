"""Escalation ticket data access."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import Conversation, Message, Ticket, TicketEvent


class TicketRepository:
    def __init__(self, db: Session):
        self.db = db

    def add_ticket_pending(self, ticket: Ticket) -> Ticket:
        """Add a ticket to the caller's transaction (no commit)."""
        self.db.add(ticket)
        return ticket

    def create_ticket(self, ticket: Ticket) -> Ticket:
        self.db.add(ticket)
        self.db.commit()
        self.db.refresh(ticket)
        return ticket

    def get_ticket(self, ticket_id: str) -> Ticket | None:
        return self.db.get(Ticket, ticket_id)

    def get_ticket_for_update(self, ticket_id: str) -> Ticket | None:
        """Lock the ticket row for an atomic status transition."""
        return self.db.scalar(
            select(Ticket).where(Ticket.id == ticket_id).with_for_update()
        )

    def get_ticket_with_context(self, ticket_id: str) -> Ticket | None:
        return self.db.scalar(
            select(Ticket)
            .options(
                selectinload(Ticket.events),
                selectinload(Ticket.conversation)
                .selectinload(Conversation.messages)
                .selectinload(Message.citations),
            )
            .where(Ticket.id == ticket_id)
        )

    def find_active_ticket_for_conversation(self, conversation_id: str) -> Ticket | None:
        """A conversation may have at most one unresolved ticket."""
        return self.db.scalar(
            select(Ticket)
            .where(
                Ticket.conversation_id == conversation_id,
                Ticket.status != "RESOLVED",
            )
            .order_by(Ticket.created_at.desc())
        )

    def list_tickets_for_conversation(self, conversation_id: str) -> list[Ticket]:
        """Every ticket raised from one conversation, newest first."""
        return list(
            self.db.scalars(
                select(Ticket)
                .where(Ticket.conversation_id == conversation_id)
                .order_by(Ticket.created_at.desc(), Ticket.id.desc())
            )
        )

    @staticmethod
    def _apply_filters(stmt, *, status: str | None, query: str | None):
        if status:
            stmt = stmt.where(Ticket.status == status)
        if query:
            needle = f"%{query.lower()}%"
            stmt = stmt.where(
                func.lower(Ticket.id).like(needle)
                | func.lower(Ticket.customer_name).like(needle)
                | func.lower(Ticket.customer_email).like(needle)
                | func.lower(Ticket.summary).like(needle)
                | func.lower(Ticket.escalation_reason).like(needle)
            )
        return stmt

    def list_tickets(
        self,
        *,
        status: str | None = None,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Ticket], int]:
        stmt = self._apply_filters(
            select(Ticket), status=status, query=query
        )

        total = self.db.scalar(
            select(func.count()).select_from(stmt.subquery())
        ) or 0
        rows = list(
            self.db.scalars(
                stmt.order_by(Ticket.created_at.desc(), Ticket.id.desc())
                .limit(limit)
                .offset(offset)
            ).all()
        )
        return rows, total

    def count_tickets_by_status(self, *, query: str | None = None) -> dict[str, int]:
        """Queue-header counts scoped to the search query, ignoring status."""
        stmt = self._apply_filters(
            select(Ticket.status, func.count()).group_by(Ticket.status),
            status=None,
            query=query,
        )
        counts = {"OPEN": 0, "IN_PROGRESS": 0, "RESOLVED": 0}
        for status, count in self.db.execute(stmt).all():
            if status in counts:
                counts[status] = count
        return counts

    def add_ticket_event_pending(
        self,
        ticket_id: str,
        event_type: str,
        *,
        old_value: str | None = None,
        new_value: str | None = None,
        actor: str = "system",
    ) -> TicketEvent:
        """Queue an event in the caller's transaction (no commit)."""
        event = TicketEvent(
            ticket_id=ticket_id,
            event_type=event_type,
            old_value=old_value,
            new_value=new_value,
            actor=actor,
        )
        self.db.add(event)
        return event

    def add_ticket_event(
        self,
        ticket_id: str,
        event_type: str,
        *,
        old_value: str | None = None,
        new_value: str | None = None,
        actor: str = "system",
    ) -> TicketEvent:
        event = self.add_ticket_event_pending(
            ticket_id,
            event_type,
            old_value=old_value,
            new_value=new_value,
            actor=actor,
        )
        self.db.commit()
        self.db.refresh(event)
        return event

    def list_ticket_events(self, ticket_id: str) -> list[TicketEvent]:
        return list(
            self.db.scalars(
                select(TicketEvent)
                .where(TicketEvent.ticket_id == ticket_id)
                .order_by(TicketEvent.created_at)
            ).all()
        )
