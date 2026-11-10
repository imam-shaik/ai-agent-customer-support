"""Escalation ticket endpoints (staff-facing)."""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_staff
from app.db.session import get_db
from app.models.entities import StaffUser
from app.schemas.ticket import (
    ConversationTicketListOut,
    EscalationCreate,
    StaffReplyCreate,
    StaffReplyOut,
    TicketDetailOut,
    TicketListOut,
    TicketStatusUpdate,
)
from app.services.ticket_service import TicketService

router = APIRouter(tags=["tickets"])


@router.post(
    "/conversations/{conversation_id}/escalations",
    response_model=TicketDetailOut,
    status_code=status.HTTP_201_CREATED,
)
def create_escalation(
    conversation_id: str,
    payload: EscalationCreate,
    db: Session = Depends(get_db),
) -> TicketDetailOut:
    """Escalate a conversation to the support team.

    404 — unknown conversation. 409 — this conversation already has an
    unresolved ticket (duplicate-retry protection; the existing ticket
    id is returned in error.details).
    """
    return TicketService(db).create_escalation(conversation_id, payload)


@router.get(
    "/conversations/{conversation_id}/escalations",
    response_model=ConversationTicketListOut,
    status_code=status.HTTP_200_OK,
)
def list_conversation_escalations(
    conversation_id: str,
    db: Session = Depends(get_db),
) -> ConversationTicketListOut:
    """Every ticket raised from ONE conversation, newest first.

    Customer-facing 'my tickets' view: id, status, summary and timestamps.
    404 — unknown conversation.
    """
    return TicketService(db).list_conversation_tickets(conversation_id)


@router.get(
    "/admin/escalations",
    response_model=TicketListOut,
    status_code=status.HTTP_200_OK,
)
def list_escalations(
    ticket_status: str | None = Query(
        default=None,
        alias="status",
        pattern="^(OPEN|IN_PROGRESS|RESOLVED)$",
        description="Filter by status.",
    ),
    q: str | None = Query(default=None, max_length=100, description="Search id/customer/summary."),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_staff: StaffUser = Depends(get_current_staff),
) -> TicketListOut:
    """List escalation tickets, newest first. 401 — not signed in."""
    return TicketService(db).list_tickets(
        status=ticket_status, query=q, limit=limit, offset=offset
    )


@router.get(
    "/admin/escalations/{ticket_id}",
    response_model=TicketDetailOut,
    status_code=status.HTTP_200_OK,
)
def get_escalation(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_staff: StaffUser = Depends(get_current_staff),
) -> TicketDetailOut:
    """Ticket detail: customer, original question, conversation with
    assistant replies + citations, lifecycle events. 401 — not signed in."""
    return TicketService(db).get_detail(ticket_id)


@router.patch(
    "/admin/escalations/{ticket_id}/status",
    response_model=TicketDetailOut,
    status_code=status.HTTP_200_OK,
)
def update_escalation_status(
    ticket_id: str,
    payload: TicketStatusUpdate,
    db: Session = Depends(get_db),
    current_staff: StaffUser = Depends(get_current_staff),
) -> TicketDetailOut:
    """Change ticket status (OPEN | IN_PROGRESS | RESOLVED).

    A status_changed event is recorded in the ticket history. 404 for an
    unknown ticket; 422 for an unsupported status value; 401 — not
    signed in.
    """
    return TicketService(db).update_status(ticket_id, payload)


@router.post(
    "/admin/escalations/{ticket_id}/replies",
    response_model=StaffReplyOut,
    status_code=status.HTTP_201_CREATED,
)
def reply_to_customer(
    ticket_id: str,
    payload: StaffReplyCreate,
    db: Session = Depends(get_db),
    current_staff: StaffUser = Depends(get_current_staff),
) -> StaffReplyOut:
    """Send one reply to the ticket's customer email from the composer.

    The reply is stored with the ticket together with an honest dispatch
    outcome (`emailDispatched` + note): without SMTP configured the
    reply is recorded as correspondence but explicitly NOT delivered.
    404 — unknown ticket; 401 — not signed in.
    """
    return TicketService(db).add_reply(ticket_id, payload, actor=current_staff.name)
