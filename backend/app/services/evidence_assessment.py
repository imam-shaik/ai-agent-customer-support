"""Evidence sufficiency signals (Phase 8B §3) — gates + verdict parsing.

THE APPLICATION DECIDES; THE MODEL JUDGES LANGUAGE.

Signals A and B are deterministic gates (config-driven, stateless):
- A relevance: the best retrieved candidate's cosine similarity must
  reach `agent_min_evidence_relevance` (uses the exact existing identity
  similarity = 1 - distance — no squashing, no invented score);
- B coverage: the fraction of the working query's material words that
  appear in the evidence must reach `agent_min_coverage_ratio`.

Signals C and D are narrow LLM verdicts parsed HERE with zero tolerance:
- `parse_evidence_verdict` — sufficiency/conflict; a conflict claim needs
  ≥2 distinct refs validated against THIS turn's evidence, and a
  non-conflicting verdict may not carry refs (malformed → 502, never
  repaired, never ignored);
- `parse_support_verdict` — the answer-support judge; `supported` must
  equal `category == "supported"` (mismatch → 502).

Deterministic gates can only make decisions MORE conservative: an LLM
"sufficient" verdict never resurrects a turn that failed a gate.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Mapping

from pydantic import ValidationError

from app.core.exceptions import GenerationFailedError
from app.core.logging import get_logger
from app.core.text import significant_words
from app.llm.base import EvidenceRef
from app.schemas.agent import EvidenceVerdict, SupportVerdict

logger = get_logger("app.evidence")

# Internal observability categories (never shown to the customer).
CATEGORY_SUPPORTED = "supported"
CATEGORY_WEAK_RELEVANCE = "weak_relevance"
CATEGORY_PARTIAL_COVERAGE = "partial_coverage"
CATEGORY_CONFLICTING = "conflicting_evidence"
CATEGORY_INSUFFICIENT = "evidence_insufficient"

_VERDICT_MESSAGE = (
    "The evidence verdict failed validation and was rejected; nothing was "
    "persisted. The turn is safe to retry."
)
_SUPPORT_MESSAGE = (
    "The answer support check failed validation and was rejected; nothing "
    "was persisted. The turn is safe to retry."
)


@dataclass(frozen=True)
class EvidenceAssessment:
    """Typed result of the sufficiency signals — observable only.

    `signals` holds counts/values with exactly defined meanings
    (top_similarity, coverage_ratio, evidence_count, llm_verdict) for
    logs and debugging. NEVER exposed to the customer, never averaged
    into a fake "confidence percentage" (§3).
    """

    category: str  # one of the CATEGORY_* constants above
    sufficient: bool
    evidence_refs: tuple[str, ...]  # E-refs considered (no chain-of-thought)
    signals: Mapping[str, float | int | bool] = field(default_factory=dict)


def relevance_gate(candidates, min_similarity: float) -> tuple[bool, float]:
    """Signal A: (passed, best cosine similarity) over retrieval candidates."""
    top = max(
        (float(candidate.cosine_similarity) for candidate in candidates),
        default=0.0,
    )
    return top >= min_similarity, top


def coverage_gate(
    query: str,
    evidence: tuple[EvidenceRef, ...],
    min_ratio: float,
) -> tuple[bool, float]:
    """Signal B: (passed, coverage ratio) of the query's material words.

    A query with zero material words (a greeting) passes vacuously —
    there is nothing to cover; the later stages still refuse to invent
    an answer. Evidence words include content and titles, matching what
    the model actually sees.
    """
    words = significant_words(query)
    if not words:
        return True, 1.0
    allowed: set[str] = set()
    for item in evidence:
        allowed |= significant_words(item.content)
        allowed |= significant_words(item.document_title)
        allowed |= significant_words(item.section_title)
    covered = len(words & allowed)
    ratio = covered / len(words)
    return ratio >= min_ratio, ratio


def parse_evidence_verdict(
    raw: str, evidence: tuple[EvidenceRef, ...]
) -> EvidenceVerdict:
    """Strict JSON + schema + app rules for call #2. Reject, never repair."""
    data = _load_object(raw, _VERDICT_MESSAGE, stage="evidence_verdict")
    try:
        verdict = EvidenceVerdict.model_validate(data)
    except ValidationError:
        logger.warning(
            "agent_structured_validation task=evidence outcome=failed reason=schema"
        )
        raise GenerationFailedError(_VERDICT_MESSAGE) from None

    if verdict.verdict == "conflicting":
        refs = verdict.conflicting_refs
        distinct = set(refs)
        valid_refs = {item.ref for item in evidence}
        # ≥2 DISTINCT refs, every one validated against this turn's map —
        # a one-ref or invented-ref conflict claim is malformed (502),
        # never repaired, never treated as a conflict.
        if len(distinct) < 2 or not distinct <= valid_refs:
            logger.warning(
                "agent_structured_validation task=evidence outcome=failed "
                "reason=conflict_refs"
            )
            raise GenerationFailedError(_VERDICT_MESSAGE) from None
    elif verdict.conflicting_refs:
        # Refs attached to a non-conflicting verdict contradict it.
        logger.warning(
            "agent_structured_validation task=evidence outcome=failed "
            "reason=unexpected_refs"
        )
        raise GenerationFailedError(_VERDICT_MESSAGE) from None

    logger.info(
        "agent_structured_validation task=evidence outcome=passed verdict=%s",
        verdict.verdict,
    )
    return verdict


def parse_support_verdict(raw: str) -> SupportVerdict:
    """Strict JSON + schema + consistency for call #4. Reject, never repair."""
    data = _load_object(raw, _SUPPORT_MESSAGE, stage="support_verdict")
    try:
        verdict = SupportVerdict.model_validate(data)
    except ValidationError:
        logger.warning(
            "agent_structured_validation task=support outcome=failed reason=schema"
        )
        raise GenerationFailedError(_SUPPORT_MESSAGE) from None

    # App-enforced cross-field rule: supported ⇔ category == "supported".
    # A mismatch is malformed output — never resolved in the model's favor.
    if verdict.supported != (verdict.category == "supported"):
        logger.warning(
            "agent_structured_validation task=support outcome=failed "
            "reason=inconsistent"
        )
        raise GenerationFailedError(_SUPPORT_MESSAGE) from None

    logger.info(
        "agent_structured_validation task=support outcome=passed supported=%s",
        verdict.supported,
    )
    return verdict


def _load_object(raw: str, safe_message: str, *, stage: str) -> dict:
    """Strict JSON object loading — no regex repair, no guessing (§12)."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning(
            "agent_structured_validation task=%s outcome=failed reason=invalid_json",
            stage,
        )
        raise GenerationFailedError(safe_message) from None
    if not isinstance(data, dict):
        logger.warning(
            "agent_structured_validation task=%s outcome=failed reason=not_an_object",
            stage,
        )
        raise GenerationFailedError(safe_message) from None
    return data
