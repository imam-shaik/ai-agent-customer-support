"""Agent decision layer orchestrator (Phase 8B §2).

THE LLM HELPS UNDERSTAND LANGUAGE.
THE KNOWLEDGE BASE PROVIDES EVIDENCE.
THE APPLICATION CONTROLS THE WORKFLOW.

One designed state machine — no scattered if/else (transition table in
docs/PHASE8B_DESIGN.md §2.3):

    input safety (deterministic patterns, 0 LLM calls) → GUARD
      → question assessment (call #1)      → clarification
      → retrieval (approved scope)         → unsupported (empty)
      → relevance gate (deterministic)     → uncertain/weak_relevance
      → coverage gate (deterministic)      → uncertain/partial_coverage
      → evidence verdict (call #2*)        → conflicting | uncertain
      → generation (call #3, 8A rules)     → uncertain/model_declined
      → support check (call #4)            → uncertain/answer_not_supported
                                            | grounded
    (* call #2 is skipped when only one evidence item exists —
      conflict is impossible, so the call would buy nothing)

ERROR is deliberately NOT a decision state in this module: provider,
schema and citation failures RAISE typed exceptions that the API layer
answers with the existing error envelopes (503/502/500) — never a 200
reply, never disguised as unsupported or uncertain (§2.4).

Determinism (§2): a decision is a pure function of (question, bounded
context, retrieved evidence, provider outputs). Deterministic gates run
first and can only make decisions MORE conservative — an LLM verdict
never resurrects a turn that failed a gate. Persistence stays in
ChatService; the LLM never chooses the next state and never touches
tickets (§11).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from pydantic import ValidationError

from app.core.config import get_settings
from app.core.exceptions import (
    EmbeddingUnavailableError,
    GenerationFailedError,
    LLMUnavailableError,
)
from app.core.logging import get_logger
from app.embeddings import EmbeddingProviderError
from app.llm import CompletionRequest, EvidenceRef, LLMProviderError, get_llm_provider
from app.llm.base import (
    TASK_ASSESSMENT,
    TASK_EVIDENCE,
    TASK_GENERATION,
    TASK_SUPPORT,
)
from app.llm.prompting import (
    ESCALATION_OFFER_TEXT,
    FALLBACK_UNSUPPORTED_TEXT,
    GUARD_TEXT,
    UNSUPPORTED_SUGGESTIONS,  # re-exported for the chat reply contract
    UNCERTAIN_TEXT,
    CONFLICT_TEXT,
    build_system_prompt,
    render_assessment_prompt,
    render_evidence_prompt,
    render_support_prompt,
    render_user_prompt,
)
from app.schemas.agent import GroundedGeneration, QuestionAssessment
from app.services.conversation_context import ContextTurn
from app.services.evidence_assessment import (
    CATEGORY_CONFLICTING,
    CATEGORY_INSUFFICIENT,
    CATEGORY_PARTIAL_COVERAGE,
    CATEGORY_WEAK_RELEVANCE,
    coverage_gate,
    parse_evidence_verdict,
    parse_support_verdict,
    relevance_gate,
)
from app.services.evidence_context import build_evidence
from app.services.retrieval_service import RetrievalService

logger = get_logger("app.agent")

# Typed decision outcomes (§2.1). ERROR is realized as the HTTP error
# envelope, not a reply kind — see module docstring.
DECISION_GROUNDED = "grounded"
DECISION_CLARIFICATION = "clarification"
DECISION_UNSUPPORTED = "unsupported"
DECISION_UNCERTAIN = "uncertain"
DECISION_CONFLICTING = "conflicting"
DECISION_GUARD = "guard"

# Uncertain sub-categories decided AFTER generation (observability only —
# every one of them shows the same typed UNCERTAIN_TEXT to the customer).
CATEGORY_MODEL_DECLINED = "model_declined"
CATEGORY_ANSWER_NOT_SUPPORTED = "answer_not_supported"

_GENERATION_SCHEMA_MESSAGE = (
    "The generated answer failed validation and was rejected; nothing was "
    "persisted. The turn is safe to retry."
)
_CITATION_MESSAGE = (
    "The generated answer cited evidence that was not retrieved for this "
    "turn and was rejected; nothing was persisted. The turn is safe to retry."
)
_ASSESSMENT_MESSAGE = (
    "The question assessment failed validation and was rejected; nothing "
    "was persisted. The turn is safe to retry."
)

# Appended to the generation prompt ONLY on the corrective re-ask (see the
# retry in run_agent_turn): names the observed defect precisely and demands
# a clean re-serialization. Content may stay the same — only the JSON
# formatting has to change.
GENERATION_CORRECTION = (
    "\n\nCRITICAL CORRECTION: your previous reply was REJECTED because it "
    "was not valid JSON — a string value was not closed before the next "
    "field. Reply AGAIN with the raw JSON object only, exactly in this "
    'shape: {"answer": "...", "citation_ids": ["E1"]} — every string value '
    "properly opened and closed, no double quote characters inside the "
    "answer text, and nothing after the closing brace. Your answer content "
    "can stay the same; only the JSON formatting needs to be correct."
)

# --- Layer 2: deterministic input safety (§7) -------------------------------
# Curated pattern screen, deliberately NOT claimed exhaustive: undetected
# attempts fall through to the normal pipeline where the structural
# trusted/untrusted boundary keeps them inert. A match short-circuits
# BEFORE any LLM call (0 calls) and never echoes prompt content.

_INJECTION_PATTERNS = (
    re.compile(
        # "ignore previous instructions" / "ignore ALL previous rules" —
        # up to two filler words between the verb and the target noun.
        r"ignore\s+(?:\w+\s+){0,2}(?:instructions|rules|prompt)",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:reveal|show|print|repeat|display)\b[^.?!]{0,80}?"
        r"(?:system\s+(?:prompt|instructions)|api\s*key|\bsecret|"
        r"(?:hidden|previous)\s+(?:instructions|rules)|"
        r"your\s+(?:instructions|rules))",
        re.IGNORECASE,
    ),
    re.compile(
        r"what\s+is\s+your\s+(?:system\s+prompt|api\s*key|hidden\s+instructions)",
        re.IGNORECASE,
    ),
    re.compile(r"forget\s+(?:everything|all\s+(?:previous|prior|above))", re.IGNORECASE),
    re.compile(
        r"developer\s+mode|act\s+as\s+(?:an?\s+)?(?:admin|administrator|developer)"
        r"|you\s+are\s+now\s+(?:no\s+longer|a\b)",
        re.IGNORECASE,
    ),
)

# Clarification content rules (§4) — defensive patterns on top of the
# structural boundary; violation is malformed model output (502), never
# repaired and never shown.
_FORBIDDEN_IN_CLARIFICATION = (
    re.compile(r"\bchunk-\d", re.IGNORECASE),
    re.compile(r"\bdoc-[a-z0-9]", re.IGNORECASE),
    re.compile(r"\bE\d+\b"),
    re.compile(r"(?:api[\s_-]?key|secret|\btoken\b|bearer\s)", re.IGNORECASE),
    re.compile(r"system\s*prompt|instructions", re.IGNORECASE),
)


@dataclass(frozen=True)
class AgentDecision:
    """Typed result of one decision turn — a pure function of its inputs.

    `category` and `escalation_offer` are application-controlled; no
    model wording is ever placed here for a non-grounded outcome (§6).
    """

    kind: str  # one of the DECISION_* constants
    text: str  # customer-facing text (typed constant, or the grounded answer)
    cited: tuple[EvidenceRef, ...] = ()  # validated refs (grounded only)
    evidence: tuple[EvidenceRef, ...] = ()
    checked_doc_ids: tuple[str, ...] = ()
    options: tuple[str, ...] = ()  # clarifying / guard options
    category: str = ""  # observability: uncertain sub-reason, guard reason
    escalation_offer: str | None = None  # attached to dead ends only (§11)


def run_agent_turn(
    db,
    *,
    question: str,
    context: tuple[ContextTurn, ...] = (),
    retrieval_query: str | None = None,
) -> AgentDecision:
    """Run the Phase 8B state machine for one customer turn.

    Raises (never returns a wrong state):
    - EmbeddingUnavailableError → 503 envelope
    - LLMUnavailableError       → 503 envelope (any of the 4 calls)
    - GenerationFailedError     → 502 envelope (malformed/invented output)
    """
    settings = get_settings()
    working_query = (retrieval_query or question).strip() or question

    # --- 0. INPUT SAFETY: deterministic short-circuit, 0 LLM calls (§7) ---
    if _is_injection_attempt(question):
        logger.info(
            "agent_decision kind=%s category=input_safety llm_calls=0",
            DECISION_GUARD,
        )
        return AgentDecision(
            kind=DECISION_GUARD,
            text=GUARD_TEXT,
            options=tuple(UNSUPPORTED_SUGGESTIONS),
            category="input_safety",
        )

    # --- provider resolved at the first LLM boundary (explicit failures) ---
    try:
        provider = get_llm_provider(settings)
    except LLMProviderError as exc:
        raise LLMUnavailableError(str(exc)) from None

    calls = {"n": 0}

    def call(
        task: str,
        *,
        user_prompt: str,
        evidence: tuple[EvidenceRef, ...] = (),
        candidate_answer: str | None = None,
        with_context: bool = False,
    ) -> str:
        calls["n"] += 1
        request = CompletionRequest(
            system_prompt=build_system_prompt(task),
            question=question,
            evidence=evidence,
            task=task,
            context=(
                tuple((turn.role, turn.content) for turn in context)
                if with_context
                else ()
            ),
            candidate_answer=candidate_answer,
            user_prompt=user_prompt,
        )
        try:
            return provider.complete(request)
        except LLMProviderError as exc:
            logger.error(
                "agent_llm_call_failed task=%s error_type=LLMProviderError", task
            )
            raise LLMUnavailableError(str(exc)) from None

    # --- 1. QUESTION ASSESSMENT (call #1, pre-retrieval) ---
    assessment_raw = call(
        TASK_ASSESSMENT,
        user_prompt=render_assessment_prompt(question, context),
        with_context=True,
    )
    assessment = _parse_question_assessment(assessment_raw)
    if assessment.ambiguous:
        logger.info(
            "agent_decision kind=%s category=ambiguous llm_calls=%d",
            DECISION_CLARIFICATION,
            calls["n"],
        )
        return AgentDecision(
            kind=DECISION_CLARIFICATION,
            text=assessment.clarification,
            options=tuple(assessment.options),
            category="ambiguous",
        )

    # --- 2. RETRIEVAL (approved scope, SQL-enforced) ---
    # Retrieval keeps the RAW question: the embedding model is typo-robust
    # and prefers full natural sentences (measured live — terse corrected
    # queries retrieve worse). The assessment's spelling-corrected
    # search_query (8b-2) feeds the deterministic COVERAGE GATE below,
    # whose raw token matching cannot survive misspelled input on its own.
    # Empty/absent correction falls back to the working query (stub
    # assessments, older prompt versions).
    coverage_query = working_query
    corrected = assessment.search_query.strip()
    if corrected:
        # Bound to the query contract; token matching only, truncation safe.
        coverage_query = corrected[: settings.retrieval_max_query_chars]

    try:
        retrieval = RetrievalService(db).retrieve(query=working_query)
    except EmbeddingProviderError as exc:
        logger.error("agent_retrieval_failed error_type=EmbeddingProviderError")
        raise EmbeddingUnavailableError(str(exc)) from None

    candidates = retrieval.candidates
    checked_doc_ids = tuple(dict.fromkeys(c.document_id for c in candidates))
    logger.info(
        "agent_retrieval_completed candidates=%d checked_docs=%d",
        len(candidates),
        len(checked_doc_ids),
    )

    # --- 3. no evidence → UNSUPPORTED: the LLM never invents (§17) ---
    if not candidates:
        decision = _dead_end(
            DECISION_UNSUPPORTED,
            FALLBACK_UNSUPPORTED_TEXT,
            category="no_evidence",
        )
        logger.info(
            "agent_decision kind=%s category=no_evidence llm_calls=%d",
            decision.kind,
            calls["n"],
        )
        return decision

    # --- 4. SIGNAL A: relevance gate (deterministic, config bar) ---
    relevant, top_similarity = relevance_gate(
        candidates, settings.agent_min_evidence_relevance
    )
    if not relevant:
        decision = _dead_end(
            DECISION_UNCERTAIN,
            UNCERTAIN_TEXT,
            checked_doc_ids=checked_doc_ids,
            category=CATEGORY_WEAK_RELEVANCE,
        )
        logger.info(
            "agent_decision kind=%s category=%s top_similarity=%.3f llm_calls=%d",
            decision.kind,
            decision.category,
            top_similarity,
            calls["n"],
        )
        return decision

    evidence = build_evidence(
        candidates,
        max_items=settings.llm_max_evidence,
        max_chars=settings.llm_evidence_max_chars,
    )

    # --- 5. SIGNAL B: coverage gate (deterministic, config bar) ---
    # Judged against the spelling-corrected query (8b-2): typos in the
    # customer's words would otherwise never match the correctly spelled
    # evidence, no matter how relevant the retrieval was. Uses the
    # corrected query so a clarification follow-up is judged against both
    # pieces (§4); falls back to the working query when absent.
    covered, coverage_ratio = coverage_gate(
        coverage_query, evidence, settings.agent_min_coverage_ratio
    )
    if not covered:
        decision = _dead_end(
            DECISION_UNCERTAIN,
            UNCERTAIN_TEXT,
            checked_doc_ids=checked_doc_ids,
            category=CATEGORY_PARTIAL_COVERAGE,
        )
        logger.info(
            "agent_decision kind=%s category=%s coverage_ratio=%.3f llm_calls=%d",
            decision.kind,
            decision.category,
            coverage_ratio,
            calls["n"],
        )
        return decision

    # --- 6. SIGNAL C: evidence verdict (call #2) ---
    # Skipped when conflict is impossible (a single evidence item).
    if len(evidence) >= 2:
        verdict_raw = call(
            TASK_EVIDENCE,
            user_prompt=render_evidence_prompt(question, evidence),
            evidence=evidence,
        )
        verdict = parse_evidence_verdict(verdict_raw, evidence)
        if verdict.verdict == "conflicting":
            decision = _dead_end(
                DECISION_CONFLICTING,
                CONFLICT_TEXT,
                checked_doc_ids=checked_doc_ids,
                category=CATEGORY_CONFLICTING,
            )
            logger.info(
                "agent_decision kind=%s category=%s llm_calls=%d",
                decision.kind,
                decision.category,
                calls["n"],
            )
            return decision
        if verdict.verdict == "insufficient":
            decision = _dead_end(
                DECISION_UNCERTAIN,
                UNCERTAIN_TEXT,
                checked_doc_ids=checked_doc_ids,
                category=CATEGORY_INSUFFICIENT,
            )
            logger.info(
                "agent_decision kind=%s category=%s llm_calls=%d",
                decision.kind,
                decision.category,
                calls["n"],
            )
            return decision

    # --- 7. GENERATION (call #3 — the Phase 8A path, unchanged rules) ---
    generation_prompt = render_user_prompt(question, evidence, context=context)

    def generate() -> GroundedGeneration:
        return _parse_generation(
            call(
                TASK_GENERATION,
                user_prompt=generation_prompt,
                evidence=evidence,
                with_context=True,
            )
        )

    try:
        generation = generate()
    except GenerationFailedError:
        # One bounded re-ask with a CORRECTIVE instruction. At temperature
        # 0 the model is near-deterministic: live runs show it sometimes
        # folds `citation_ids` into the answer string (an unclosed string
        # → malformed JSON), and an identical retry then returns the same
        # malformed bytes — verified against the live model, the identical
        # retry can never succeed when the failure is deterministic. The
        # corrective re-ask names the exact defect (unclosed string, raw
        # JSON only) and recovered 4/4 malformed live samples while the
        # strict parse below stays the sole judge (still no application-
        # side JSON repair). A second failure raises the same 502.
        # Semantic rejections (invented citation) happen after parsing
        # and are never retried.
        logger.warning("agent_generation_retry outcome=attempted mode=corrective")
        corrective_request = CompletionRequest(
            system_prompt=build_system_prompt(TASK_GENERATION),
            question=question,
            evidence=evidence,
            task=TASK_GENERATION,
            context=tuple((turn.role, turn.content) for turn in context),
            candidate_answer=None,
            user_prompt=generation_prompt + GENERATION_CORRECTION,
        )
        try:
            generation = _parse_generation(provider.complete(corrective_request))
        except LLMProviderError as exc:
            logger.error(
                "agent_llm_call_failed task=%s error_type=LLMProviderError",
                TASK_GENERATION,
            )
            raise LLMUnavailableError(str(exc)) from None

    cited, unknown = _validate_citation_ids(generation.citation_ids, evidence)
    if unknown:
        logger.warning(
            "agent_citation_validation outcome=failed unknown_refs=%d", len(unknown)
        )
        raise GenerationFailedError(_CITATION_MESSAGE)

    if not cited:
        # Schema-valid but the model declined to ground (Q2 decision):
        # evidence existed → UNCERTAIN, never disguised as unsupported.
        # The model's wording is discarded; the typed text is shown.
        decision = _dead_end(
            DECISION_UNCERTAIN,
            UNCERTAIN_TEXT,
            checked_doc_ids=checked_doc_ids,
            category=CATEGORY_MODEL_DECLINED,
            evidence=evidence,
        )
        logger.info(
            "agent_decision kind=%s category=%s llm_calls=%d",
            decision.kind,
            decision.category,
            calls["n"],
        )
        return decision

    # --- 8. SIGNAL D: answer support check (call #4, narrow judge) ---
    support_raw = call(
        TASK_SUPPORT,
        user_prompt=render_support_prompt(question, evidence, generation.answer),
        evidence=evidence,
        candidate_answer=generation.answer,
    )
    support = parse_support_verdict(support_raw)
    if not support.supported:
        # The candidate answer EXCEEDED its evidence: discarded — never
        # persisted, never shown (§3 signal D).
        decision = _dead_end(
            DECISION_UNCERTAIN,
            UNCERTAIN_TEXT,
            checked_doc_ids=checked_doc_ids,
            category=CATEGORY_ANSWER_NOT_SUPPORTED,
            evidence=evidence,
        )
        logger.info(
            "agent_decision kind=%s category=%s llm_calls=%d",
            decision.kind,
            decision.category,
            calls["n"],
        )
        return decision

    logger.info(
        "agent_decision kind=%s citations=%d llm_calls=%d",
        DECISION_GROUNDED,
        len(cited),
        calls["n"],
    )
    return AgentDecision(
        kind=DECISION_GROUNDED,
        text=generation.answer,
        cited=cited,
        evidence=evidence,
        checked_doc_ids=checked_doc_ids,
        category="grounded",
    )


# ---------------------------------------------------------------------------
# deterministic helpers (no LLM involvement)
# ---------------------------------------------------------------------------


def _is_injection_attempt(question: str) -> bool:
    """Layer-2 input safety screen (§7): pattern match → GUARD, 0 calls."""
    return any(pattern.search(question) for pattern in _INJECTION_PATTERNS)


def _dead_end(
    kind: str,
    text: str,
    *,
    checked_doc_ids: tuple[str, ...] = (),
    category: str,
    evidence: tuple[EvidenceRef, ...] = (),
) -> AgentDecision:
    """A dead-end outcome: typed text only + the escalation offer (§11)."""
    return AgentDecision(
        kind=kind,
        text=text,
        evidence=evidence,
        checked_doc_ids=checked_doc_ids,
        category=category,
        escalation_offer=ESCALATION_OFFER_TEXT,
    )


def _parse_question_assessment(raw: str) -> QuestionAssessment:
    """Strict JSON + schema + app cross-field rules for call #1 (§4).

    Reject, never repair: a malformed assessment is a 502, never
    reinterpreted into a decision.
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning(
            "agent_structured_validation task=assessment outcome=failed reason=invalid_json"
        )
        raise GenerationFailedError(_ASSESSMENT_MESSAGE) from None
    if not isinstance(data, dict):
        logger.warning(
            "agent_structured_validation task=assessment outcome=failed reason=not_an_object"
        )
        raise GenerationFailedError(_ASSESSMENT_MESSAGE) from None
    try:
        assessment = QuestionAssessment.model_validate(data)
    except ValidationError:
        logger.warning(
            "agent_structured_validation task=assessment outcome=failed reason=schema"
        )
        raise GenerationFailedError(_ASSESSMENT_MESSAGE) from None

    if not assessment.ambiguous:
        # No pretending ambiguity with a payload attached.
        if assessment.clarification or assessment.options:
            logger.warning(
                "agent_structured_validation task=assessment outcome=failed "
                "reason=unexpected_clarification"
            )
            raise GenerationFailedError(_ASSESSMENT_MESSAGE) from None
        logger.info(
            "agent_structured_validation task=assessment outcome=passed ambiguous=false"
        )
        return assessment

    # ambiguous=true ⇒ EXACTLY ONE concise, valid question (§4).
    clarification = assessment.clarification
    checks = (
        10 <= len(clarification) <= 300,
        clarification.endswith("?"),
        clarification.count("?") == 1,
        1 <= len(assessment.options) <= 4,
        all(1 <= len(option) <= 80 for option in assessment.options),
        not any(p.search(clarification) for p in _FORBIDDEN_IN_CLARIFICATION),
        not any(
            p.search(option) for option in assessment.options
            for p in _FORBIDDEN_IN_CLARIFICATION
        ),
    )
    if not all(checks):
        logger.warning(
            "agent_structured_validation task=assessment outcome=failed reason=invalid_clarification"
        )
        raise GenerationFailedError(_ASSESSMENT_MESSAGE) from None

    logger.info(
        "agent_structured_validation task=assessment outcome=passed ambiguous=true"
    )
    return assessment


def _parse_generation(raw: str) -> GroundedGeneration:
    """Strict JSON + schema validation. No regex repair, no guessing (§12)."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning(
            "agent_structured_validation task=generation outcome=failed reason=invalid_json"
        )
        raise GenerationFailedError(_GENERATION_SCHEMA_MESSAGE) from None
    if not isinstance(data, dict):
        logger.warning(
            "agent_structured_validation task=generation outcome=failed reason=not_an_object"
        )
        raise GenerationFailedError(_GENERATION_SCHEMA_MESSAGE) from None
    try:
        generation = GroundedGeneration.model_validate(data)
    except ValidationError:
        logger.warning(
            "agent_structured_validation task=generation outcome=failed reason=schema"
        )
        raise GenerationFailedError(_GENERATION_SCHEMA_MESSAGE) from None
    logger.info("agent_structured_validation task=generation outcome=passed")
    return generation


def _validate_citation_ids(
    citation_ids: list[str],
    evidence: tuple[EvidenceRef, ...],
) -> tuple[tuple[EvidenceRef, ...], tuple[str, ...]]:
    """Split declared refs into (valid, unknown); order kept, duplicates dropped."""
    by_ref = {item.ref: item for item in evidence}
    seen: set[str] = set()
    cited: list[EvidenceRef] = []
    unknown: list[str] = []
    for citation_id in citation_ids:
        if citation_id not in by_ref:
            unknown.append(citation_id)
            continue
        if citation_id in seen:
            continue
        seen.add(citation_id)
        cited.append(by_ref[citation_id])
    return tuple(cited), tuple(unknown)
