"""Retrieval routes (Phase 7 §14) — development/internal search endpoint.

POST /api/v1/retrieval/search returns structured evidence candidates for
a query. It is intentionally NOT part of the customer chat flow: the
frontend stays on the approved mock agent until Phase 8, and this
endpoint never generates natural-language answers.
"""

from dataclasses import asdict

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.exceptions import EmbeddingUnavailableError
from app.db.session import get_db
from app.embeddings import EmbeddingProviderError
from app.schemas.retrieval import (
    RetrievalCandidateOut,
    RetrievalSearchOut,
    RetrievalSearchRequest,
)
from app.services.retrieval_service import RetrievalService

router = APIRouter(prefix="/retrieval", tags=["retrieval"])


@router.post("/search", response_model=RetrievalSearchOut)
def search(
    payload: RetrievalSearchRequest,
    db: Session = Depends(get_db),
) -> RetrievalSearchOut:
    """Search approved knowledge for possible evidence candidates.

    Validation: empty/whitespace queries, oversized queries and limits
    outside the configured range are rejected with the standard 422
    envelope. Provider failures surface as an explicit 503 — never as
    fake vectors or silently-empty results pretending to be complete.
    """
    try:
        result = RetrievalService(db).retrieve(query=payload.query, limit=payload.limit)
    except EmbeddingProviderError as exc:
        # Message comes from our own config guidance — safe to expose,
        # contains no keys and no provider internals.
        raise EmbeddingUnavailableError(str(exc)) from exc

    return RetrievalSearchOut(
        embedding_model=result.embedding_model,
        limit=result.limit,
        min_cosine_similarity=result.min_cosine_similarity,
        candidate_count=len(result.candidates),
        candidates=[
            RetrievalCandidateOut(**asdict(candidate)) for candidate in result.candidates
        ],
    )
