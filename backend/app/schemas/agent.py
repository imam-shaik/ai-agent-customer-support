"""Internal LLM structured-output schemas (Phase 8A §11, extended 8B §2).

Deliberately independent from the camelCase API contracts: this is the
exact JSON the MODEL must produce, validated with zero tolerance —
required fields stay required (a missing `citation_ids` is a contract
violation, not "no citations"), unknown keys are rejected, and types are
never guessed at. Malformed output is rejected upstream of persistence,
never repaired (§12).

Every 8B decision schema is `extra="forbid"` too: evidence text that
claims "also emit an extra field" cannot change any output shape — the
application re-validates regardless of what any prompt content says.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class GroundedGeneration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str = Field(min_length=1, max_length=4000)
    # Required on purpose: the model must state its citations explicitly,
    # even when the honest answer is an empty list (no grounding).
    citation_ids: list[str] = Field(max_length=50)


class QuestionAssessment(BaseModel):
    """Call #1 (Phase 8B §4): is the question materially ambiguous?

    Cross-field rules are enforced by the APPLICATION after validation
    (ambiguous=false ⇒ empty clarification/options; ambiguous=true ⇒ one
    bounded question) — never trusted from the model alone.
    """

    model_config = ConfigDict(extra="forbid")

    ambiguous: bool
    # Exactly one concise routing question; empty when not ambiguous.
    clarification: str = Field(default="", max_length=300)
    # 0–4 short options the customer can pick from; [] when not ambiguous.
    options: list[str] = Field(default_factory=list, max_length=4)
    # Spelling-corrected, self-contained search text for retrieval (8b-2).
    # Optional by contract: absent/empty ⇒ the raw question is used exactly
    # as before (stub assessments, older prompts). Internal only — it feeds
    # embedding + the deterministic coverage gate, never the customer.
    search_query: str = Field(default="", max_length=400)
    # Small-talk classification (8b-4): greetings, pleasantries, identity
    # and capability questions are conversation, not support questions —
    # the application replies with a fixed greeting and never retrieves.
    # Optional by contract: absent ⇒ false (stub, older prompts).
    small_talk: bool = False


class EvidenceVerdict(BaseModel):
    """Call #2 (Phase 8B §3, signal C): sufficiency/conflict verdict.

    `conflicting_refs` must hold ≥2 distinct refs validated against this
    turn's evidence map — checked by the application, never assumed.
    """

    model_config = ConfigDict(extra="forbid")

    verdict: Literal["sufficient", "conflicting", "insufficient"]
    conflicting_refs: list[str] = Field(default_factory=list, max_length=50)


class SupportVerdict(BaseModel):
    """Call #4 (Phase 8B §3, signal D): does the candidate answer stay
    within its evidence?

    App-enforced consistency: `supported` must equal
    `category == "supported"` — a mismatch is malformed (502), never
    resolved in the model's favor.
    """

    model_config = ConfigDict(extra="forbid")

    supported: bool
    category: Literal["supported", "exceeds_evidence", "insufficient_support"]
