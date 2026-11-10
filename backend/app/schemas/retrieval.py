"""Retrieval API contracts (Phase 7 §14).

Development/internal endpoint: returns structured evidence candidates
only. There is deliberately no answer field of any kind — Phase 8 wires
retrieval to the agent. ApiModel's extra="forbid" means a client cannot
even ask for `includeChallengeFixtures` over HTTP (422); that switch
exists only in the service layer for tests and CLI tooling.
"""

from pydantic import Field

from app.schemas.common import ApiModel
from app.schemas.document import KnowledgeStatus


class RetrievalSearchRequest(ApiModel):
    query: str = Field(min_length=1)
    # None → settings.retrieval_top_k_default; bounds checked against
    # settings.retrieval_top_k_max in the service (config, not magic numbers).
    limit: int | None = None


class RetrievalCandidateOut(ApiModel):
    chunk_id: str
    document_id: str
    document_title: str
    section_id: str
    section_title: str
    chunk_index: int
    content: str
    knowledge_status: KnowledgeStatus
    source: str | None = None
    # Exact cosine values (see report §A.4): distance from pgvector's <=>,
    # similarity = 1 - distance. Never a generic "score".
    cosine_distance: float
    cosine_similarity: float


class RetrievalSearchOut(ApiModel):
    embedding_model: str
    limit: int
    min_cosine_similarity: float
    candidate_count: int
    # Evidence candidates only — never an answer, never a sufficiency claim.
    candidates: list[RetrievalCandidateOut]
