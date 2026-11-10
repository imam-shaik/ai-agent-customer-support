"""Conversation/message/citation/feedback data access.

No business rules here — repositories only read and write rows.
"""

from datetime import datetime, timezone

from sqlalchemy import case, select
from sqlalchemy.orm import Session, selectinload

from app.models import Citation, Conversation, Feedback, Message


class ConversationRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_conversation(self) -> Conversation:
        conversation = Conversation()
        self.db.add(conversation)
        self.db.commit()
        self.db.refresh(conversation)
        return conversation

    def get_conversation(self, conversation_id: str) -> Conversation | None:
        return self.db.get(Conversation, conversation_id)

    def conversation_has_messages(self, conversation_id: str) -> bool:
        return (
            self.db.query(Message)
            .filter(Message.conversation_id == conversation_id)
            .limit(1)
            .first()
            is not None
        )

    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        reply: dict | None = None,
        *,
        client_request_id: str | None = None,
        reply_to_message_id: str | None = None,
    ) -> Message:
        message = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            reply=reply,
            client_request_id=client_request_id,
            reply_to_message_id=reply_to_message_id,
        )
        self.db.add(message)
        conversation = self.db.get(Conversation, conversation_id)
        if conversation is not None:
            conversation.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(message)
        return message

    def get_message(self, message_id: str) -> Message | None:
        return self.db.get(Message, message_id)

    def get_user_message_by_client_request(
        self, conversation_id: str, client_request_id: str
    ) -> Message | None:
        """The stored customer turn for a stable request id (Phase 9)."""
        return self.db.scalar(
            select(Message).where(
                Message.conversation_id == conversation_id,
                Message.client_request_id == client_request_id,
                Message.role == "user",
            )
        )

    def get_assistant_reply(self, user_message_id: str) -> Message | None:
        """The single assistant reply bound to a customer turn (Phase 9)."""
        return self.db.scalar(
            select(Message).where(Message.reply_to_message_id == user_message_id)
        )

    def add_assistant_turn(
        self,
        conversation_id: str,
        *,
        content: str,
        reply: dict,
        reply_to_message_id: str,
        citations: list[dict],
    ) -> Message:
        """Persist an assistant reply and its citations atomically.

        Idempotent replay must never surface a grounded answer whose
        citation rows failed to commit, so the message and every citation
        are written in one transaction. The unique `reply_to_message_id`
        index also makes concurrent retries safe: only one turns commits.
        """
        message = Message(
            conversation_id=conversation_id,
            role="assistant",
            content=content,
            reply=reply,
            reply_to_message_id=reply_to_message_id,
        )
        self.db.add(message)
        conversation = self.db.get(Conversation, conversation_id)
        if conversation is not None:
            conversation.updated_at = datetime.now(timezone.utc)
        self.db.flush()
        for citation in citations:
            self.db.add(
                Citation(
                    message_id=message.id,
                    document_id=citation["document_id"],
                    section_ref=citation["section_ref"],
                    chunk_id=citation.get("chunk_id"),
                    evidence_snapshot=citation["evidence_snapshot"],
                )
            )
        self.db.commit()
        self.db.refresh(message)
        return message

    def add_citation(
        self,
        message_id: str,
        document_id: str,
        section_ref: str,
        evidence_snapshot: dict,
        chunk_id: str | None = None,
    ) -> Citation:
        citation = Citation(
            message_id=message_id,
            document_id=document_id,
            section_ref=section_ref,
            chunk_id=chunk_id,
            evidence_snapshot=evidence_snapshot,
        )
        self.db.add(citation)
        self.db.commit()
        self.db.refresh(citation)
        return citation

    def list_citations(self, message_id: str) -> list[Citation]:
        return list(
            self.db.scalars(
                select(Citation)
                .where(Citation.message_id == message_id)
                .order_by(Citation.created_at)
            ).all()
        )

    def list_conversation_messages(self, conversation_id: str) -> list[Message]:
        return list(
            self.db.scalars(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                # A customer turn and its reply can share a timestamp; the
                # customer message always precedes the reply.
                .order_by(
                    Message.created_at,
                    case((Message.role == "user", 0), else_=1),
                )
            ).all()
        )

    def list_conversation_messages_with_details(
        self, conversation_id: str
    ) -> list[Message]:
        """History read: messages with citations and feedback eager-loaded."""
        return list(
            self.db.scalars(
                select(Message)
                .options(
                    selectinload(Message.citations),
                    selectinload(Message.feedback),
                )
                .where(Message.conversation_id == conversation_id)
                # A customer turn and its reply can share a timestamp; the
                # customer message always precedes the reply.
                .order_by(
                    Message.created_at,
                    case((Message.role == "user", 0), else_=1),
                )
            ).all()
        )

    def get_feedback(self, message_id: str) -> Feedback | None:
        return self.db.scalar(select(Feedback).where(Feedback.message_id == message_id))

    def add_feedback(self, message_id: str, rating: str, reason: str | None) -> Feedback:
        feedback = Feedback(message_id=message_id, rating=rating, reason=reason)
        self.db.add(feedback)
        self.db.commit()
        self.db.refresh(feedback)
        return feedback

    def get_conversation_with_messages(self, conversation_id: str) -> Conversation | None:
        return self.db.scalar(
            select(Conversation)
            .options(selectinload(Conversation.messages).selectinload(Message.citations))
            .where(Conversation.id == conversation_id)
        )
