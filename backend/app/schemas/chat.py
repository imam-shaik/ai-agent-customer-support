"""Chat contracts.

The `reply` union mirrors the frontend's AgentReply kinds one-to-one so
Phase 9 can consume responses without rewriting the UI:

    frontend (mock)      API kind               spec vocabulary
    -------------------  ---------------------  ---------------------
    grounded             grounded               grounded_answer
    clarifying           clarifying             clarifying_question
    unsupported          unsupported            insufficient_evidence
    (new in 8B)          uncertain              uncertain_answer
    conflict             conflict               conflicting_evidence
    guard                guard                  safe_refusal
    escalation_offer     escalation_offer       (human hand-off offer)
    error                error                  provider_error

Phase 8B deltas (additive only — every existing member is unchanged):
- NEW `uncertain` kind: evidence existed but could not support a
  complete answer (the five internal categories all show one typed text).
- `escalation_offer` field on the three dead-end kinds (unsupported,
  uncertain, conflict): an OFFER attached to the outcome that dead-ended,
  not a separate turn kind — one turn is one reply (design §10).
"""

from datetime import datetime
from typing import Annotated, Literal, Union
from uuid import UUID

from pydantic import Field

from app.schemas.common import ApiModel
from app.schemas.feedback import FeedbackOut


class CitationOut(ApiModel):
    doc_id: str
    section_id: str
    # Evidence snapshot captured when the answer was generated.
    document_title: str | None = None
    section_title: str | None = None
    snippet: str | None = None


class GroundedReply(ApiModel):
    kind: Literal["grounded"]
    text: str
    citations: list[CitationOut]


class ClarifyingReply(ApiModel):
    kind: Literal["clarifying"]
    text: str
    options: list[str]


class UnsupportedReply(ApiModel):
    kind: Literal["unsupported"]
    text: str
    checked_doc_ids: list[str]
    suggestions: list[str]
    # Fixed application-controlled offer sentence (None = not offered).
    escalation_offer: str | None = None


class UncertainReply(ApiModel):
    """Evidence existed but could not safely support the complete answer."""

    kind: Literal["uncertain"]
    text: str
    checked_doc_ids: list[str]
    suggestions: list[str]
    escalation_offer: str | None = None


class ConflictReply(ApiModel):
    kind: Literal["conflict"]
    text: str
    checked_doc_ids: list[str]
    suggestions: list[str]
    escalation_offer: str | None = None


class GuardReply(ApiModel):
    kind: Literal["guard"]
    text: str
    options: list[str]


class EscalationOfferReply(ApiModel):
    kind: Literal["escalation_offer"]
    text: str


class ErrorReply(ApiModel):
    kind: Literal["error"]
    text: str


AgentReply = Annotated[
    Union[
        GroundedReply,
        ClarifyingReply,
        UnsupportedReply,
        UncertainReply,
        ConflictReply,
        GuardReply,
        EscalationOfferReply,
        ErrorReply,
    ],
    Field(discriminator="kind"),
]


class ChatSessionCreate(ApiModel):
    """Empty body reserved for future metadata (locale, device, …)."""


class ChatSessionOut(ApiModel):
    conversation_id: str
    created_at: datetime


class MessageCreate(ApiModel):
    content: str = Field(min_length=1, max_length=4000)
    # Phase 9: optional at the API compatibility boundary, always sent by
    # the customer frontend. Retries reuse the same id so a completed turn
    # is replayed instead of creating a duplicate.
    client_request_id: UUID | None = None


class MessageOut(ApiModel):
    id: str
    role: Literal["user", "assistant", "system"]
    content: str
    created_at: datetime
    reply: AgentReply | None = None
    citations: list[CitationOut] = []
    # Echoed for the customer turn so the client can reconcile its
    # optimistic message and retry with the same id.
    client_request_id: str | None = None
    # Recorded feedback (assistant messages only; None when unrated).
    feedback: FeedbackOut | None = None


class ChatTurnOut(ApiModel):
    conversation_id: str
    user_message: MessageOut
    assistant_message: MessageOut


class ActiveTicketOut(ApiModel):
    """Minimal active-ticket view used to restore the ticket chip after a
    page reload. Full ticket detail remains available from the Phase 5
    admin endpoint."""

    id: str
    status: Literal["OPEN", "IN_PROGRESS", "RESOLVED"]
    summary: str
    original_question: str
    customer_name: str
    customer_email: str
    customer_phone: str | None = None
    created_at: datetime
    message_count: int


class ChatHistoryOut(ApiModel):
    conversation_id: str
    messages: list[MessageOut]
    active_ticket: ActiveTicketOut | None = None
