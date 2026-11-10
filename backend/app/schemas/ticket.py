"""Escalation ticket contracts."""

from datetime import datetime
from typing import Literal

from pydantic import EmailStr, Field

from app.schemas.chat import MessageOut
from app.schemas.common import ApiModel

TicketStatus = Literal["OPEN", "IN_PROGRESS", "RESOLVED"]
TicketPriority = Literal["normal", "high"]
# How a reply leaves the app: "smtp" = the server sends it (requires
# SMTP_HOST); "gmail" = the UI opens Gmail compose pre-filled and the
# staff member completes delivery there (no SMTP config needed).
ReplyChannel = Literal["smtp", "gmail"]


class EscalationCreate(ApiModel):
    customer_name: str = Field(min_length=2, max_length=200)
    customer_email: EmailStr
    # Optional second contact channel. When provided it must look like a
    # phone number (digits with optional +, spaces, dashes, parentheses);
    # when omitted it is stored as NULL — never an empty string.
    customer_phone: str | None = Field(
        default=None,
        max_length=32,
        pattern=r"^\+?[0-9][0-9()\-\s]{6,31}$",
    )
    summary: str = Field(min_length=3, max_length=300)
    original_question: str = Field(min_length=1, max_length=4000)
    escalation_reason: str = Field(
        default="Escalated from customer conversation", max_length=300
    )
    priority: TicketPriority = "normal"


class TicketStatusUpdate(ApiModel):
    status: TicketStatus
    actor: str = Field(default="staff", max_length=100)
    # Phase 10: optional optimistic-concurrency guard. The staff client
    # always sends the status it last read; legacy callers may omit it.
    expected_status: TicketStatus | None = None


class StaffReplyCreate(ApiModel):
    """Body of one staff reply, sent to the ticket's customer email."""

    message: str = Field(min_length=1, max_length=4000)
    # "smtp" (default): server-side dispatch. "gmail": the UI opens Gmail
    # compose pre-filled; delivery completes in Gmail, outside this app.
    channel: ReplyChannel = "smtp"


class StaffReplyOut(ApiModel):
    """Stored record of a sent reply — what, to whom, delivered or not."""

    id: str
    staff_name: str
    body: str
    sent_to: str
    email_dispatched: bool
    dispatch_note: str | None = None
    dispatch_channel: Literal["smtp", "gmail"] | None = None
    created_at: datetime


class TicketEventOut(ApiModel):
    id: str
    event_type: str
    old_value: str | None = None
    new_value: str | None = None
    actor: str
    created_at: datetime


class TicketSummaryOut(ApiModel):
    id: str
    conversation_id: str
    customer_name: str
    customer_email: str
    customer_phone: str | None = None
    summary: str
    escalation_reason: str
    status: TicketStatus
    priority: TicketPriority
    created_at: datetime
    updated_at: datetime


class TicketDetailOut(TicketSummaryOut):
    original_question: str
    messages: list[MessageOut] = []
    events: list[TicketEventOut] = []
    # Staff replies sent from the composer, oldest first. Every reply
    # reports whether its email actually went out (honest dispatch
    # state) — the UI renders this stored history, never local state.
    replies: list[StaffReplyOut] = []


class ConversationTicketOut(ApiModel):
    """Customer-facing row for the 'my tickets' section: what was raised,
    when, and where it stands now — no staff internals."""

    id: str
    status: TicketStatus
    summary: str
    created_at: datetime
    updated_at: datetime


class ConversationTicketListOut(ApiModel):
    """All tickets raised from ONE conversation, newest first."""

    conversation_id: str
    total: int
    items: list[ConversationTicketOut]


class TicketListOut(ApiModel):
    items: list[TicketSummaryOut]
    total: int
    limit: int
    offset: int
    # Phase 10: status totals for the queue header. Counts are scoped to
    # the search query but ignore the status filter; keys are canonical
    # uppercase API statuses.
    counts: dict[str, int] = Field(default_factory=dict)
