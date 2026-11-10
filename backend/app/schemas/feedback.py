"""Feedback contracts."""

from datetime import datetime
from typing import Literal

from pydantic import Field

from app.schemas.common import ApiModel


class FeedbackCreate(ApiModel):
    rating: Literal["helpful", "not_helpful"]
    reason: str | None = Field(default=None, max_length=300)


class FeedbackOut(ApiModel):
    id: str
    message_id: str
    rating: Literal["helpful", "not_helpful"]
    reason: str | None = None
    created_at: datetime
