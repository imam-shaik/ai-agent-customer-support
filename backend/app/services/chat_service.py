"""Chat service: conversation lifecycle, message turns, feedback.

Owns the rule that conversation history is append-only evidence: the
assistant's typed reply and its citations are persisted exactly once,
at answer time, and never regenerated.

Phase 8B: the turn runs the decision orchestrator
(app/services/agent_service.run_agent_turn) with a BOUNDED context
window and the composed working query (app/services/
conversation_context), while the API contract (reply union, citations,
envelopes) stays exactly as approved — one new `uncertain` kind and the
`escalation_offer` field on dead-end replies.

Phase 9: customer turns are idempotent. A stable `clientRequestId`
identifies one submission; retries replay the stored turn instead of
creating duplicates, and the unique `reply_to_message_id` index makes a
concurrent retry unable to persist a second assistant reply. Assistant
messages and their citations commit atomically.

Failure/retry semantics (§18): the customer message is persisted BEFORE
generation (never lost); nothing generated is persisted unless schema and
citation validation passed; re-posting the SAME content while it is still
the unanswered tail reuses that row (legacy clients), and a re-posted
request id always reuses its turn (Phase 9 clients).
"""

from pydantic import TypeAdapter
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.core.exceptions import ConflictError, NotFoundError
from app.core.logging import get_logger
from app.models import Message
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.ticket_repository import TicketRepository
from app.schemas.chat import (
    ActiveTicketOut,
    AgentReply,
    ChatHistoryOut,
    ChatSessionOut,
    CitationOut,
    ChatTurnOut,
    MessageCreate,
    MessageOut,
)
from app.schemas.feedback import FeedbackCreate, FeedbackOut
from app.services import agent_service
from app.services.conversation_context import build_context, compose_retrieval_query

logger = get_logger("app.chat")

_reply_adapter = TypeAdapter(AgentReply)


def _citation_out(citation) -> CitationOut:
    snapshot = citation.evidence_snapshot or {}
    return CitationOut(
        doc_id=citation.document_id,
        section_id=citation.section_ref,
        document_title=snapshot.get("document_title"),
        section_title=snapshot.get("section_title"),
        snippet=snapshot.get("snippet"),
    )


def _feedback_out(feedback) -> FeedbackOut | None:
    if feedback is None:
        return None
    return FeedbackOut(
        id=feedback.id,
        message_id=feedback.message_id,
        rating=feedback.rating,
        reason=feedback.reason,
        created_at=feedback.created_at,
    )


def _message_out(message: Message, citations: list, feedback=None) -> MessageOut:
    reply = _reply_adapter.validate_python(message.reply) if message.reply else None
    return MessageOut(
        id=message.id,
        role=message.role,
        content=message.content,
        created_at=message.created_at,
        reply=reply,
        citations=[_citation_out(citation) for citation in citations],
        client_request_id=message.client_request_id,
        feedback=_feedback_out(feedback),
    )


class ChatService:
    def __init__(self, db):
        self.db = db
        self.repo = ConversationRepository(db)

    def create_session(self) -> ChatSessionOut:
        conversation = self.repo.create_conversation()
        logger.info("conversation_created conversation_id=%s", conversation.id)
        return ChatSessionOut(
            conversation_id=conversation.id, created_at=conversation.created_at
        )

    # ------------------------------------------------------------------
    # turn resolution (legacy tail-reuse + Phase 9 request-id replay)
    # ------------------------------------------------------------------

    def _resolve_turn(
        self,
        conversation_id: str,
        payload: MessageCreate,
        existing: list[Message],
    ) -> tuple[Message, list[Message], Message | None]:
        """Return (customer message, history before it, replay assistant).

        A non-None third element means the turn already completed and must
        be returned verbatim: no agent call, no writes.
        """
        request_id = str(payload.client_request_id) if payload.client_request_id else None

        if request_id is None:
            # Legacy path: reuse the identical unanswered tail only. This
            # does NOT protect a completed turn (Phase 9 adds request ids).
            tail = existing[-1] if existing else None
            reused = (
                tail is not None
                and tail.role == "user"
                and tail.content == payload.content
            )
            if reused:
                logger.info(
                    "message_retry_reused conversation_id=%s", conversation_id
                )
                return tail, existing[:-1], None
            user_message = self.repo.add_message(
                conversation_id, role="user", content=payload.content
            )
            return user_message, existing, None

        user_message = self.repo.get_user_message_by_client_request(
            conversation_id, request_id
        )
        if user_message is None:
            try:
                user_message = self.repo.add_message(
                    conversation_id,
                    role="user",
                    content=payload.content,
                    client_request_id=request_id,
                )
                return user_message, existing, None
            except IntegrityError:
                # Concurrent duplicate insert: the other request won the
                # unique (conversation_id, client_request_id) index. Load
                # it and take the replay path.
                self.db.rollback()
                user_message = self.repo.get_user_message_by_client_request(
                    conversation_id, request_id
                )
                if user_message is None:  # pragma: no cover - defensive
                    raise

        # --- replay / retry path -------------------------------------
        if user_message.content != payload.content:
            logger.warning(
                "idempotency_key_conflict conversation_id=%s request_id=%s",
                conversation_id,
                request_id,
            )
            raise ConflictError(
                "This request id was already used for a different message.",
                details={"clientRequestId": request_id},
            )

        assistant = self.repo.get_assistant_reply(user_message.id)
        if assistant is not None:
            logger.info(
                "message_idempotent_replay conversation_id=%s request_id=%s",
                conversation_id,
                request_id,
            )
            return user_message, [], assistant

        # Unanswered turn: only retryable while it is still the last row.
        # If the customer moved on, an out-of-order reply would corrupt the
        # transcript, so the client is told to reload the conversation.
        latest = self.repo.list_conversation_messages(conversation_id)
        if not latest or latest[-1].id != user_message.id:
            raise ConflictError(
                "This message can no longer be retried because the conversation has moved on.",
                details={"clientRequestId": request_id},
            )

        logger.info(
            "message_retry_reused conversation_id=%s request_id=%s",
            conversation_id,
            request_id,
        )
        return user_message, latest[:-1], None

    # ------------------------------------------------------------------
    # write path
    # ------------------------------------------------------------------

    def post_message(self, conversation_id: str, payload: MessageCreate) -> ChatTurnOut:
        if self.repo.get_conversation(conversation_id) is None:
            raise NotFoundError("Conversation not found.")

        logger.info(
            "message_received conversation_id=%s chars=%d",
            conversation_id,
            len(payload.content),
        )

        existing = self.repo.list_conversation_messages(conversation_id)
        user_message, history, replay = self._resolve_turn(
            conversation_id, payload, existing
        )

        if replay is not None:
            citations = self.repo.list_citations(replay.id)
            return ChatTurnOut(
                conversation_id=conversation_id,
                user_message=_message_out(user_message, [], user_message.feedback),
                assistant_message=_message_out(replay, citations, replay.feedback),
            )

        # --- bounded context + working query (Phase 8B §4) ---
        # The full history never reaches a prompt: only the last N
        # messages, each truncated. If the previous assistant reply was
        # `clarifying`, retrieval and the coverage gate also see the
        # message that triggered it.
        settings = get_settings()
        context = build_context(
            history,
            max_messages=settings.agent_context_max_messages,
            max_chars=settings.agent_context_max_chars,
        )
        working_query = compose_retrieval_query(history, payload.content)

        # --- decision + validation (agent core) ---
        # Raises 503/502 BEFORE any assistant row exists: an invalid or
        # unavailable decision is never persisted (§12, §18).
        decision = agent_service.run_agent_turn(
            self.repo.db,
            question=payload.content,
            context=context,
            retrieval_query=working_query,
        )

        # --- build the typed reply from the validated decision ---
        citation_rows: list[dict] = []
        if decision.kind == agent_service.DECISION_GROUNDED:
            citation_outs = [
                CitationOut(
                    doc_id=item.document_id,
                    section_id=item.section_id,
                    document_title=item.document_title,
                    section_title=item.section_title,
                    snippet=item.content,
                )
                for item in decision.cited
            ]
            citation_rows = [
                {
                    "document_id": item.document_id,
                    "section_ref": item.section_id,
                    "chunk_id": item.chunk_id,
                    "evidence_snapshot": {
                        "document_title": item.document_title,
                        "section_title": item.section_title,
                        "snippet": item.content,
                    },
                }
                for item in decision.cited
            ]
            reply_dict = {
                "kind": "grounded",
                "text": decision.text,
                "citations": [
                    citation.model_dump(mode="json") for citation in citation_outs
                ],
            }
        elif decision.kind == agent_service.DECISION_CLARIFICATION:
            reply_dict = {
                "kind": "clarifying",
                "text": decision.text,
                "options": list(decision.options),
            }
        elif decision.kind == agent_service.DECISION_GREETING:
            reply_dict = {
                "kind": "greeting",
                "text": decision.text,
                "options": list(decision.options),
            }
        elif decision.kind == agent_service.DECISION_GUARD:
            reply_dict = {
                "kind": "guard",
                "text": decision.text,
                "options": list(decision.options),
            }
        else:
            # Dead ends (unsupported / uncertain / conflicting): typed text
            # only — no model wording — plus checked docs, suggestions and
            # the escalation offer (§11). The LLM never touches tickets.
            kind = {
                agent_service.DECISION_UNSUPPORTED: "unsupported",
                agent_service.DECISION_UNCERTAIN: "uncertain",
                agent_service.DECISION_CONFLICTING: "conflict",
            }[decision.kind]
            reply_dict = {
                "kind": kind,
                "text": decision.text,
                "checked_doc_ids": list(decision.checked_doc_ids),
                "suggestions": list(agent_service.UNSUPPORTED_SUGGESTIONS),
                "escalation_offer": decision.escalation_offer,
            }

        # --- persist assistant + citations ATOMICALLY ---
        # The unique reply_to index is the concurrency guard: if another
        # retry already completed this turn, we discard our generated
        # answer and return the stored one. No duplicate rows, no
        # duplicate citations.
        try:
            assistant_message = self.repo.add_assistant_turn(
                conversation_id,
                content=reply_dict["text"],
                reply=reply_dict,
                reply_to_message_id=user_message.id,
                citations=citation_rows,
            )
        except IntegrityError:
            self.db.rollback()
            winner = self.repo.get_assistant_reply(user_message.id)
            if winner is None:  # pragma: no cover - defensive
                raise
            logger.info(
                "assistant_persist_conflict conversation_id=%s request_id=%s",
                conversation_id,
                user_message.client_request_id,
            )
            return ChatTurnOut(
                conversation_id=conversation_id,
                user_message=_message_out(user_message, [], user_message.feedback),
                assistant_message=_message_out(
                    winner, self.repo.list_citations(winner.id), winner.feedback
                ),
            )

        persisted_citations = self.repo.list_citations(assistant_message.id)

        logger.info(
            "reply_generated conversation_id=%s kind=%s citations=%d",
            conversation_id,
            reply_dict["kind"],
            len(persisted_citations),
        )

        return ChatTurnOut(
            conversation_id=conversation_id,
            user_message=_message_out(user_message, [], user_message.feedback),
            assistant_message=_message_out(
                assistant_message, persisted_citations, assistant_message.feedback
            ),
        )

    # ------------------------------------------------------------------
    # read path
    # ------------------------------------------------------------------

    def get_history(self, conversation_id: str) -> ChatHistoryOut:
        if self.repo.get_conversation(conversation_id) is None:
            raise NotFoundError("Conversation not found.")

        messages = self.repo.list_conversation_messages_with_details(conversation_id)
        ticket = TicketRepository(self.db).find_active_ticket_for_conversation(
            conversation_id
        )
        active_ticket = (
            ActiveTicketOut(
                id=ticket.id,
                status=ticket.status,
                summary=ticket.summary,
                original_question=ticket.original_question,
                customer_name=ticket.customer_name,
                customer_email=ticket.customer_email,
                customer_phone=ticket.customer_phone,
                created_at=ticket.created_at,
                message_count=len(messages),
            )
            if ticket is not None
            else None
        )

        return ChatHistoryOut(
            conversation_id=conversation_id,
            messages=[
                _message_out(message, list(message.citations), message.feedback)
                for message in messages
            ],
            active_ticket=active_ticket,
        )

    # ------------------------------------------------------------------
    # feedback
    # ------------------------------------------------------------------

    def submit_feedback(
        self, message_id: str, payload: FeedbackCreate
    ) -> FeedbackOut:
        message = self.repo.get_message(message_id)
        if message is None:
            raise NotFoundError("Message not found.")
        if message.role != "assistant":
            raise ConflictError("Feedback can only be recorded on assistant messages.")
        if self.repo.get_feedback(message_id) is not None:
            raise ConflictError(
                "Feedback has already been recorded for this message.",
                details={"messageId": message_id},
            )

        feedback = self.repo.add_feedback(message_id, payload.rating, payload.reason)
        logger.info(
            "feedback_recorded message_id=%s rating=%s", message_id, payload.rating
        )
        return FeedbackOut(
            id=feedback.id,
            message_id=feedback.message_id,
            rating=feedback.rating,
            reason=feedback.reason,
            created_at=feedback.created_at,
        )
