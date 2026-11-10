"""Message feedback endpoint."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.feedback import FeedbackCreate, FeedbackOut
from app.services.chat_service import ChatService

router = APIRouter(tags=["feedback"])


@router.post(
    "/messages/{message_id}/feedback",
    response_model=FeedbackOut,
    status_code=status.HTTP_201_CREATED,
)
def record_feedback(
    message_id: str,
    payload: FeedbackCreate,
    db: Session = Depends(get_db),
) -> FeedbackOut:
    """Record helpful/not-helpful feedback for an assistant message.

    404 — unknown message. 409 — feedback already recorded, or the
    message is not an assistant message. 422 — invalid rating/reason.
    """
    return ChatService(db).submit_feedback(message_id, payload)
