"""Chat endpoints."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.chat import (
    ChatHistoryOut,
    ChatSessionCreate,
    ChatSessionOut,
    ChatTurnOut,
    MessageCreate,
)
from app.schemas.feedback import FeedbackCreate, FeedbackOut
from app.services.chat_service import ChatService

router = APIRouter(tags=["chat"])


@router.post(
    "/chat/sessions",
    response_model=ChatSessionOut,
    status_code=status.HTTP_201_CREATED,
)
def create_chat_session(
    _payload: ChatSessionCreate | None = None,
    db: Session = Depends(get_db),
) -> ChatSessionOut:
    """Start a new support conversation."""
    return ChatService(db).create_session()


@router.post(
    "/chat/sessions/{conversation_id}/messages",
    response_model=ChatTurnOut,
    status_code=status.HTTP_200_OK,
)
def post_chat_message(
    conversation_id: str,
    payload: MessageCreate,
    db: Session = Depends(get_db),
) -> ChatTurnOut:
    """Send a customer message and receive the assistant reply turn.

    The reply is a typed, discriminated union (grounded / clarifying /
    unsupported / uncertain / conflict / guard / escalation_offer / error).
    Internal prompts and provider details are never part of the response.

    Phase 9: `clientRequestId` makes a turn idempotent — re-posting the
    same id returns the stored turn instead of creating a duplicate.
    """
    return ChatService(db).post_message(conversation_id, payload)


@router.get(
    "/chat/sessions/{conversation_id}/messages",
    response_model=ChatHistoryOut,
    status_code=status.HTTP_200_OK,
)
def get_chat_messages(
    conversation_id: str,
    db: Session = Depends(get_db),
) -> ChatHistoryOut:
    """Read the conversation transcript for reload (Phase 9).

    Read-only: messages with typed replies, citations, recorded feedback,
    and the active ticket summary. 404 for an unknown conversation.
    """
    return ChatService(db).get_history(conversation_id)
