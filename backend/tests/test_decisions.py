"""Phase 8B decision-state tests — the §18 matrix, key-free and network-free.

Every typed outcome of the state machine (docs/PHASE8B_DESIGN.md §2.3)
is proven through `run_agent_turn` with the two pipeline seams patched
(shared helpers in `agent_harness.py`):

    GROUNDED ............... TestGroundedPath
    UNSUPPORTED ............ TestUnsupported
    UNCERTAIN (5 categories) TestUncertain
    CLARIFICATION .......... TestAmbiguity + TestContextBounds
    CONFLICTING_EVIDENCE ... TestConflict
    ERROR (typed envelopes)  TestErrorSemantics
    determinism + gates-only-more-conservative ... TestDeterminism

The GUARD state (input safety) lives in test_injection.py.

Design decisions asserted here:
- Q2: `citation_ids: []` → UNCERTAIN/model_declined, never unsupported;
- 4-call budget: assessment → evidence* → generation → support
  (*skipped when conflict is impossible); GUARD = 0 calls;
- ERROR is an exception → 503/502 envelope, never a 200 reply;
- deterministic gates run first and can only be MORE conservative;
- unsupported ≠ uncertain: different states, different texts, both
  carry the escalation offer.
"""

import json

import pytest
from fastapi.testclient import TestClient

from app.core.exceptions import GenerationFailedError, LLMUnavailableError
from app.llm import LLMProviderError
from app.llm.base import TASK_ASSESSMENT, TASK_EVIDENCE, TASK_GENERATION, TASK_SUPPORT
from app.llm.prompting import (
    CONFLICT_TEXT,
    ESCALATION_OFFER_TEXT,
    FALLBACK_UNSUPPORTED_TEXT,
    GREETING_TEXT,
    UNCERTAIN_TEXT,
)
from app.services.agent_service import (
    CATEGORY_ANSWER_NOT_SUPPORTED,
    CATEGORY_MODEL_DECLINED,
    DECISION_CLARIFICATION,
    DECISION_CONFLICTING,
    DECISION_GREETING,
    DECISION_GROUNDED,
    DECISION_UNCERTAIN,
    DECISION_UNSUPPORTED,
    run_agent_turn,
)
from app.services.conversation_context import (
    ContextTurn,
    build_context,
    compose_retrieval_query,
)
from app.services.evidence_assessment import (
    CATEGORY_INSUFFICIENT,
    CATEGORY_PARTIAL_COVERAGE,
    CATEGORY_WEAK_RELEVANCE,
    coverage_gate,
)
from tests.agent_harness import (
    QUESTION,
    ScriptedProvider,
    _candidate,
    _patch_provider,
    _patch_retrieval,
)

_AMBIGUOUS_JSON = json.dumps(
    {
        "ambiguous": True,
        "clarification": "Is this about signing in or about billing?",
        "options": ["Signing in", "Billing"],
    }
)
_GROUNDED_JSON = json.dumps(
    {"answer": "Reset it from the login page.", "citation_ids": ["E1"]}
)


def _tasks(provider: ScriptedProvider) -> list[str]:
    return [request.task for request in provider.calls]


# ---------------------------------------------------------------------------
# GROUNDED — the full happy path and the call budget (§2, §3)
# ---------------------------------------------------------------------------


class TestGroundedPath:
    def test_four_call_budget_in_order(self, monkeypatch: pytest.MonkeyPatch):
        """assessment → evidence → generation → support: exactly 4 calls,
        in the designed order, then GROUNDED."""
        _patch_retrieval(monkeypatch, (_candidate(1), _candidate(2)))
        provider = ScriptedProvider(
            {
                TASK_GENERATION: _GROUNDED_JSON,
            }
        )
        _patch_provider(monkeypatch, provider)

        decision = run_agent_turn(None, question=QUESTION)

        assert decision.kind == DECISION_GROUNDED
        assert decision.category == "grounded"
        assert decision.escalation_offer is None
        assert [item.ref for item in decision.cited] == ["E1"]
        assert _tasks(provider) == [
            TASK_ASSESSMENT,
            TASK_EVIDENCE,
            TASK_GENERATION,
            TASK_SUPPORT,
        ]

    def test_single_evidence_item_skips_conflict_verdict(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """Conflict is impossible with one item → call #2 buys nothing
        and is skipped: 3 calls, still GROUNDED."""
        _patch_retrieval(monkeypatch, (_candidate(1),))
        provider = ScriptedProvider({TASK_GENERATION: _GROUNDED_JSON})
        _patch_provider(monkeypatch, provider)

        decision = run_agent_turn(None, question=QUESTION)

        assert decision.kind == DECISION_GROUNDED
        assert _tasks(provider) == [
            TASK_ASSESSMENT,
            TASK_GENERATION,
            TASK_SUPPORT,
        ]

    def test_grounded_is_deterministic_across_runs(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """Same inputs → same decision (§2 determinism)."""
        _patch_retrieval(monkeypatch, (_candidate(1), _candidate(2)))
        _patch_provider(
            monkeypatch, ScriptedProvider({TASK_GENERATION: _GROUNDED_JSON})
        )
        first = run_agent_turn(None, question=QUESTION)
        _patch_provider(
            monkeypatch, ScriptedProvider({TASK_GENERATION: _GROUNDED_JSON})
        )
        second = run_agent_turn(None, question=QUESTION)

        assert (first.kind, first.text, first.category) == (
            second.kind,
            second.text,
            second.category,
        )
        assert [item.ref for item in first.cited] == [
            item.ref for item in second.cited
        ]


# ---------------------------------------------------------------------------
# UNSUPPORTED — no evidence at all (≠ UNCERTAIN, §2, §17)
# ---------------------------------------------------------------------------


class TestUnsupported:
    def test_empty_retrieval_returns_typed_unsupported(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        _patch_retrieval(monkeypatch, ())
        provider = ScriptedProvider("I would have invented an answer!")
        _patch_provider(monkeypatch, provider)

        decision = run_agent_turn(None, question=QUESTION)

        assert decision.kind == DECISION_UNSUPPORTED
        assert decision.text == FALLBACK_UNSUPPORTED_TEXT
        assert decision.category == "no_evidence"
        assert decision.checked_doc_ids == ()
        # Dead end → escalation offer attached (§11):
        assert decision.escalation_offer == ESCALATION_OFFER_TEXT
        # The model is never asked to invent an answer without evidence:
        assert provider.generation_calls() == []
        assert _tasks(provider) == [TASK_ASSESSMENT]

    def test_unsupported_is_not_uncertain(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """The two dead ends are distinct states with distinct texts —
        they are never conflated (§2)."""
        _patch_retrieval(monkeypatch, ())
        _patch_provider(monkeypatch, ScriptedProvider({}))
        unsupported = run_agent_turn(None, question=QUESTION)

        # Uncertain: evidence existed but could not support the answer.
        _patch_retrieval(monkeypatch, (_candidate(1),))
        _patch_provider(
            monkeypatch,
            ScriptedProvider(
                {
                    TASK_GENERATION: json.dumps(
                        {"answer": "Maybe something in settings?", "citation_ids": []}
                    )
                }
            ),
        )
        uncertain = run_agent_turn(None, question=QUESTION)

        assert unsupported.kind == DECISION_UNSUPPORTED
        assert uncertain.kind == DECISION_UNCERTAIN
        assert unsupported.text != uncertain.text
        assert unsupported.text == FALLBACK_UNSUPPORTED_TEXT
        assert uncertain.text == UNCERTAIN_TEXT


# ---------------------------------------------------------------------------
# UNCERTAIN — five categories, one typed text (§3, §6, Q2)
# ---------------------------------------------------------------------------


class TestUncertain:
    def test_weak_relevance_gate_returns_uncertain_without_evidence_call(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """Signal A fails (top similarity below the config bar) →
        UNCERTAIN/weak_relevance before ANY evidence verdict (§3)."""
        _patch_retrieval(
            monkeypatch, (_candidate(1, similarity=0.01),)
        )
        provider = ScriptedProvider(
            {TASK_EVIDENCE: json.dumps({"verdict": "sufficient", "conflicting_refs": []})}
        )
        _patch_provider(monkeypatch, provider)

        decision = run_agent_turn(None, question=QUESTION)

        assert decision.kind == DECISION_UNCERTAIN
        assert decision.category == CATEGORY_WEAK_RELEVANCE
        assert decision.text == UNCERTAIN_TEXT
        assert decision.escalation_offer == ESCALATION_OFFER_TEXT
        assert decision.checked_doc_ids == ("doc-password-help",)
        # The deterministic gate short-circuits before call #2:
        assert provider.calls_for(TASK_EVIDENCE) == []
        assert provider.generation_calls() == []

    def test_partial_coverage_returns_uncertain(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """Signal B fails: 'refund' has no coverage in the evidence →
        UNCERTAIN/partial_coverage (cancel+refund scenario, §3)."""
        _patch_retrieval(
            monkeypatch,
            (
                _candidate(
                    1,
                    content="You can cancel your subscription at any time from billing.",
                ),
            ),
        )
        provider = ScriptedProvider({})
        _patch_provider(monkeypatch, provider)

        decision = run_agent_turn(
            None, question="Can I cancel and get a refund?"
        )

        assert decision.kind == DECISION_UNCERTAIN
        assert decision.category == CATEGORY_PARTIAL_COVERAGE
        assert decision.text == UNCERTAIN_TEXT
        assert decision.escalation_offer == ESCALATION_OFFER_TEXT
        assert provider.generation_calls() == []

    def test_model_declining_grounding_is_uncertain_not_unsupported(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """Q2: citation_ids: [] with retrieved evidence → UNCERTAIN/
        model_declined; the model's wording is discarded (§6)."""
        _patch_retrieval(monkeypatch, (_candidate(1),))
        _patch_provider(
            monkeypatch,
            ScriptedProvider(
                {
                    TASK_GENERATION: json.dumps(
                        {
                            "answer": "I am not sure, but maybe it is in settings?",
                            "citation_ids": [],
                        }
                    )
                }
            ),
        )

        decision = run_agent_turn(None, question=QUESTION)

        assert decision.kind == DECISION_UNCERTAIN
        assert decision.category == CATEGORY_MODEL_DECLINED
        assert decision.text == UNCERTAIN_TEXT
        assert "maybe" not in decision.text
        assert decision.evidence  # evidence existed — not unsupported
        assert decision.escalation_offer == ESCALATION_OFFER_TEXT

    def test_answer_exceeding_evidence_is_discarded_as_uncertain(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """Signal D: the support judge says the candidate answer exceeds
        its evidence → UNCERTAIN/answer_not_supported; the candidate is
        never shown (§3)."""
        _patch_retrieval(monkeypatch, (_candidate(1), _candidate(2)))
        _patch_provider(
            monkeypatch,
            ScriptedProvider(
                {
                    TASK_GENERATION: json.dumps(
                        {
                            "answer": "Your account is refunded within 24 hours, guaranteed.",
                            "citation_ids": ["E1"],
                        }
                    ),
                    TASK_SUPPORT: json.dumps(
                        {"supported": False, "category": "exceeds_evidence"}
                    ),
                }
            ),
        )

        decision = run_agent_turn(None, question=QUESTION)

        assert decision.kind == DECISION_UNCERTAIN
        assert decision.category == CATEGORY_ANSWER_NOT_SUPPORTED
        assert decision.text == UNCERTAIN_TEXT
        assert "24 hours" not in decision.text  # candidate discarded
        assert decision.escalation_offer == ESCALATION_OFFER_TEXT

    def test_insufficient_evidence_verdict_is_uncertain(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """Signal C: relevant evidence exists but does not cover the
        question → UNCERTAIN/evidence_insufficient, before generation."""
        _patch_retrieval(monkeypatch, (_candidate(1), _candidate(2)))
        provider = ScriptedProvider(
            {
                TASK_EVIDENCE: json.dumps(
                    {"verdict": "insufficient", "conflicting_refs": []}
                )
            }
        )
        _patch_provider(monkeypatch, provider)

        decision = run_agent_turn(None, question=QUESTION)

        assert decision.kind == DECISION_UNCERTAIN
        assert decision.category == CATEGORY_INSUFFICIENT
        assert decision.text == UNCERTAIN_TEXT
        assert decision.escalation_offer == ESCALATION_OFFER_TEXT
        assert provider.generation_calls() == []

    def test_greeting_coverage_is_vacuous_but_still_never_invents(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """A greeting has zero material words: the coverage gate passes
        vacuously (nothing to cover) — but the model still declines to
        ground, so the outcome is UNCERTAIN, never an invented answer."""
        words_free, ratio = coverage_gate("hello there", (), 0.75)
        assert words_free is True and ratio == 1.0

        _patch_retrieval(monkeypatch, (_candidate(1, similarity=0.06),))
        _patch_provider(
            monkeypatch,
            ScriptedProvider(
                {
                    TASK_GENERATION: json.dumps(
                        {"answer": "Hello! How can I help?", "citation_ids": []}
                    )
                }
            ),
        )
        decision = run_agent_turn(None, question="hello there")

        assert decision.kind == DECISION_UNCERTAIN
        assert decision.category == CATEGORY_MODEL_DECLINED
        assert decision.text == UNCERTAIN_TEXT

    def test_coverage_accepts_e_restored_base_form(self):
        """Deterministic morphology fix (8b-2): the query's 'arrived'
        stems to 'arriv', but the evidence carries 'arrive' — the
        e-restoration variant covers it. Unrelated words still do not
        match: no edit distance, no prefixes."""
        from app.llm.base import EvidenceRef

        evidence = (
            EvidenceRef(
                ref="E1",
                chunk_id="chunk-0001",
                document_id="account-access",
                document_title="Account Access & Recovery",
                section_id="password-reset",
                section_title="Password reset",
                content=(
                    "Select Forgot password? and we send a reset link. "
                    "If the email does not arrive, check the spam folder."
                ),
            ),
        )
        covered, ratio = coverage_gate("password reset not arrived", evidence, 0.75)
        assert covered is True and ratio == 1.0

        # Still honest about genuinely different words:
        missed, ratio_missed = coverage_gate("pasword rest", evidence, 0.75)
        assert missed is False and ratio_missed == 0.0


# ---------------------------------------------------------------------------
# CLARIFICATION + bounded context (§4)
# ---------------------------------------------------------------------------


class TestAmbiguity:
    def test_ambiguous_question_returns_single_clarifying_question(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """Call #1 decides ambiguity BEFORE retrieval: exactly one concise
        question + options, one LLM call, not a dead end (no escalation)."""
        _patch_retrieval(monkeypatch, (_candidate(1),))
        provider = ScriptedProvider({TASK_ASSESSMENT: _AMBIGUOUS_JSON})
        _patch_provider(monkeypatch, provider)

        decision = run_agent_turn(
            None, question="my account isn't working"
        )

        assert decision.kind == DECISION_CLARIFICATION
        assert decision.category == "ambiguous"
        assert decision.text == "Is this about signing in or about billing?"
        assert decision.options == ("Signing in", "Billing")
        assert decision.text.count("?") == 1
        assert decision.text.endswith("?")
        # Clarification short-circuits before retrieval/generation:
        assert _tasks(provider) == [TASK_ASSESSMENT]
        # A clarification is an open turn, not a dead end (§11):
        assert decision.escalation_offer is None

    def test_two_questions_in_clarification_is_rejected(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        _patch_retrieval(monkeypatch, ())
        _patch_provider(
            monkeypatch,
            ScriptedProvider(
                {
                    TASK_ASSESSMENT: json.dumps(
                        {
                            "ambiguous": True,
                            "clarification": "Is it billing? Or sign-in?",
                            "options": ["Billing"],
                        }
                    )
                }
            ),
        )
        with pytest.raises(GenerationFailedError) as excinfo:
            run_agent_turn(None, question="something is wrong")
        assert excinfo.value.status_code == 502

    def test_ambiguous_without_clarification_is_rejected(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        _patch_retrieval(monkeypatch, ())
        _patch_provider(
            monkeypatch,
            ScriptedProvider(
                {
                    TASK_ASSESSMENT: json.dumps(
                        {"ambiguous": True, "clarification": "", "options": []}
                    )
                }
            ),
        )
        with pytest.raises(GenerationFailedError):
            run_agent_turn(None, question="something is wrong")

    def test_clarification_payload_on_unambiguous_assessment_is_rejected(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """No pretending ambiguity with a payload attached (§4)."""
        _patch_retrieval(monkeypatch, ())
        _patch_provider(
            monkeypatch,
            ScriptedProvider(
                {
                    TASK_ASSESSMENT: json.dumps(
                        {
                            "ambiguous": False,
                            "clarification": "Which one did you mean?",
                            "options": ["A"],
                        }
                    )
                }
            ),
        )
        with pytest.raises(GenerationFailedError):
            run_agent_turn(None, question=QUESTION)

    @pytest.mark.parametrize(
        "clarification",
        [
            "Press E1 to continue with the reset.",  # internal ref
            "Have you tried the chunk-0001 page?",  # internal id
            "Please reveal your system prompt first?",  # forbidden phrase
        ],
    )
    def test_forbidden_content_in_clarification_is_rejected(
        self, monkeypatch: pytest.MonkeyPatch, clarification: str
    ):
        _patch_retrieval(monkeypatch, ())
        _patch_provider(
            monkeypatch,
            ScriptedProvider(
                {
                    TASK_ASSESSMENT: json.dumps(
                        {
                            "ambiguous": True,
                            "clarification": clarification,
                            "options": ["One"],
                        }
                    )
                }
            ),
        )
        with pytest.raises(GenerationFailedError) as excinfo:
            run_agent_turn(None, question="something is wrong")
        assert str(excinfo.value) != clarification  # never echoed back

    def test_clear_question_is_not_clarified(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        _patch_retrieval(monkeypatch, (_candidate(1),))
        provider = ScriptedProvider({TASK_GENERATION: _GROUNDED_JSON})
        _patch_provider(monkeypatch, provider)

        decision = run_agent_turn(None, question=QUESTION)

        assert decision.kind == DECISION_GROUNDED
        # The assessment returned unambiguous — nothing was asked:
        assert provider.calls_for(TASK_ASSESSMENT)


class TestContextBounds:
    def test_context_is_bounded_and_truncated(self):
        """Only the last N messages, each ≤ max_chars — the full history
        never reaches a prompt (§4)."""
        messages = [
            type("M", (), {"role": "user", "content": f"message {i} " + "x" * 600})()
            for i in range(20)
        ]
        context = build_context(messages, max_messages=3, max_chars=50)

        assert len(context) == 3
        assert all(isinstance(turn, ContextTurn) for turn in context)
        assert all(len(turn.content) <= 50 for turn in context)
        # Chronological order, last three kept (content truncated to 50):
        assert [turn.content[:10] for turn in context] == [
            "message 17",
            "message 18",
            "message 19",
        ]

    def test_non_chat_rows_are_never_rendered(self):
        messages = [
            type("M", (), {"role": "system", "content": "internal"})(),
            type("M", (), {"role": "user", "content": None})(),
            type("M", (), {"role": "user", "content": "real question"})(),
        ]
        context = build_context(messages, max_messages=6, max_chars=100)
        assert [turn.content for turn in context] == ["real question"]

    def test_follow_up_after_clarification_composes_working_query(self):
        """Clarifying reply → working query is trigger + current message
        (each ≤ 400 chars), so turn-2 retrieval sees turn-1 context."""
        history = [
            type(
                "M",
                (),
                {"role": "user", "content": "my account isn't working", "reply": None},
            )(),
            type(
                "M",
                (),
                {
                    "role": "assistant",
                    "content": "Could you tell me more?",
                    "reply": {"kind": "clarifying"},
                },
            )(),
        ]
        query = compose_retrieval_query(history, "signing in")
        assert query == "my account isn't working signing in"

        # Piece caps: each side truncated at 400 chars.
        long_trigger = "a" * 500
        history[0].content = long_trigger
        query = compose_retrieval_query(history, "b" * 500)
        assert query == f"{'a' * 400} {'b' * 400}"

    def test_normal_history_keeps_current_message_as_query(self):
        history = [
            type(
                "M",
                (),
                {"role": "user", "content": QUESTION, "reply": None},
            )(),
            type(
                "M",
                (),
                {
                    "role": "assistant",
                    "content": "Reset it from the login page.",
                    "reply": {"kind": "grounded"},
                },
            )(),
        ]
        assert compose_retrieval_query(history, "When am I billed?") == (
            "When am I billed?"
        )


# ---------------------------------------------------------------------------
# CONFLICTING_EVIDENCE — material same-fact disagreement (§5)
# ---------------------------------------------------------------------------


class TestConflict:
    def _conflicting_provider(self) -> ScriptedProvider:
        return ScriptedProvider(
            {
                TASK_EVIDENCE: json.dumps(
                    {
                        "verdict": "conflicting",
                        "conflicting_refs": ["E1", "E2"],
                    }
                )
            }
        )

    def test_conflict_verdict_returns_conflicting_state(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        _patch_retrieval(monkeypatch, (_candidate(1), _candidate(2)))
        provider = self._conflicting_provider()
        _patch_provider(monkeypatch, provider)

        decision = run_agent_turn(None, question=QUESTION)

        assert decision.kind == DECISION_CONFLICTING
        assert decision.category == "conflicting_evidence"
        assert decision.text == CONFLICT_TEXT
        assert decision.escalation_offer == ESCALATION_OFFER_TEXT
        # The docs the agent actually checked (deduplicated):
        assert decision.checked_doc_ids == ("doc-password-help",)
        # Conflict stops the machine BEFORE generation — no half-answer:
        assert provider.generation_calls() == []

    @pytest.mark.parametrize(
        "refs",
        [
            ["E1"],  # single ref: disagreement needs ≥2 items
            ["E99"],  # invented ref
            ["E1", "E99"],  # mixed valid/invented
            ["E1", "E1"],  # duplicates are not two distinct items
        ],
    )
    def test_invalid_conflict_refs_are_rejected_never_repaired(
        self, monkeypatch: pytest.MonkeyPatch, refs: list[str]
    ):
        _patch_retrieval(monkeypatch, (_candidate(1), _candidate(2)))
        _patch_provider(
            monkeypatch,
            ScriptedProvider(
                {
                    TASK_EVIDENCE: json.dumps(
                        {"verdict": "conflicting", "conflicting_refs": refs}
                    )
                }
            ),
        )
        with pytest.raises(GenerationFailedError) as excinfo:
            run_agent_turn(None, question=QUESTION)
        assert excinfo.value.status_code == 502
        assert "E99" not in str(excinfo.value)

    def test_non_conflicting_verdict_may_not_carry_refs(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        _patch_retrieval(monkeypatch, (_candidate(1), _candidate(2)))
        _patch_provider(
            monkeypatch,
            ScriptedProvider(
                {
                    TASK_EVIDENCE: json.dumps(
                        {"verdict": "sufficient", "conflicting_refs": ["E1", "E2"]}
                    )
                }
            ),
        )
        with pytest.raises(GenerationFailedError):
            run_agent_turn(None, question=QUESTION)

    def test_chat_endpoint_returns_conflict_reply_with_escalation(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ):
        """Through the REAL endpoint: the scripted conflict surfaces as
        the typed `conflict` reply — checked docs, suggestions, the
        escalation offer, and zero citations."""
        _patch_retrieval(monkeypatch, (_candidate(1), _candidate(2)))
        _patch_provider(monkeypatch, self._conflicting_provider())

        session = client.post("/api/v1/chat/sessions", json={}).json()
        response = client.post(
            f"/api/v1/chat/sessions/{session['conversationId']}/messages",
            json={"content": QUESTION},
        )

        assert response.status_code == 200
        reply = response.json()["assistantMessage"]["reply"]
        assert reply["kind"] == "conflict"
        assert reply["text"] == CONFLICT_TEXT
        assert reply["escalationOffer"] == ESCALATION_OFFER_TEXT
        assert reply["suggestions"]
        assert isinstance(reply["checkedDocIds"], list)
        assert response.json()["assistantMessage"]["citations"] == []


# ---------------------------------------------------------------------------
# ESCALATION BOUNDARY (§11, §12) — the agent never writes tickets
# ---------------------------------------------------------------------------


class TestEscalationBoundary:
    def test_agent_turns_create_zero_tickets(
        self, client: TestClient, db_session, monkeypatch: pytest.MonkeyPatch
    ):
        """No decision path — grounded or dead end — may auto-create a
        ticket. A human hand-off stays the customer-submitted Phase 5
        endpoint (duplicate prevention included)."""
        from sqlalchemy import func, select

        from app.models import Ticket

        def ticket_count() -> int:
            return db_session.scalar(select(func.count()).select_from(Ticket))

        # Grounded turn (REAL retrieval — citations persist with FKs to
        # real documents; the session fixture indexed the corpus):
        _patch_provider(
            monkeypatch, ScriptedProvider({TASK_GENERATION: _GROUNDED_JSON})
        )
        session = client.post("/api/v1/chat/sessions", json={}).json()
        grounded = client.post(
            f"/api/v1/chat/sessions/{session['conversationId']}/messages",
            json={"content": QUESTION},
        )
        assert grounded.status_code == 200
        assert ticket_count() == 0

        # Dead-end turn (scripted conflict — the most "escalation-worthy"
        # outcome still creates nothing):
        _patch_retrieval(monkeypatch, (_candidate(1), _candidate(2)))
        _patch_provider(
            monkeypatch,
            ScriptedProvider(
                {
                    TASK_EVIDENCE: json.dumps(
                        {"verdict": "conflicting", "conflicting_refs": ["E1", "E2"]}
                    )
                }
            ),
        )
        conflict = client.post(
            f"/api/v1/chat/sessions/{session['conversationId']}/messages",
            json={"content": QUESTION},
        )
        assert conflict.status_code == 200
        assert conflict.json()["assistantMessage"]["reply"]["kind"] == "conflict"
        assert ticket_count() == 0

        # The explicit customer submission still works and is the ONLY
        # way a ticket comes into existence (Phase 5 endpoint, unchanged):
        escalation = client.post(
            f"/api/v1/conversations/{session['conversationId']}/escalations",
            json={
                "customerName": "Priya Raman",
                "customerEmail": "priya@harborlight.org",
                "summary": "Conflicting answers about password reset",
                "originalQuestion": QUESTION,
                "escalationReason": "Need a human to confirm the policy",
            },
        )
        assert escalation.status_code == 201
        assert ticket_count() == 1


# ---------------------------------------------------------------------------
# ERROR — typed envelopes, never a disguised 200 reply (§2.4, §18)
# ---------------------------------------------------------------------------


class TestErrorSemantics:
    """Provider/schema failures RAISE typed exceptions (503/502). The
    pipeline never converts them into unsupported/uncertain/guard."""

    @pytest.mark.parametrize(
        "task,extra",
        [
            (TASK_ASSESSMENT, {}),
            (TASK_EVIDENCE, {}),  # 2 candidates → call #2 runs
            (TASK_GENERATION, {}),
            (TASK_SUPPORT, {TASK_GENERATION: _GROUNDED_JSON}),
        ],
    )
    def test_llm_failure_at_any_stage_is_503(
        self,
        monkeypatch: pytest.MonkeyPatch,
        task: str,
        extra: dict,
    ):
        responses = {task: LLMProviderError("provider unreachable")}
        responses.update(extra)
        _patch_retrieval(monkeypatch, (_candidate(1), _candidate(2)))
        _patch_provider(monkeypatch, ScriptedProvider(responses))

        with pytest.raises(LLMUnavailableError) as excinfo:
            run_agent_turn(None, question=QUESTION)

        assert excinfo.value.status_code == 503
        assert excinfo.value.code == "LLM_PROVIDER_UNAVAILABLE"

    def test_provider_factory_failure_is_503(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        _patch_retrieval(monkeypatch, (_candidate(1),))
        _patch_provider(
            monkeypatch, LLMProviderError("NVIDIA_API_KEY is not configured")
        )
        with pytest.raises(LLMUnavailableError) as excinfo:
            run_agent_turn(None, question=QUESTION)
        assert excinfo.value.status_code == 503

    @pytest.mark.parametrize(
        "task,raw",
        [
            (TASK_ASSESSMENT, "not json at all"),
            (TASK_ASSESSMENT, '{"ambiguous": "yes"}'),  # wrong type
            (TASK_EVIDENCE, "[]"),  # not an object
            (TASK_EVIDENCE, '{"verdict": "maybe"}'),  # unknown verdict
            (TASK_SUPPORT, '{"supported": true}'),  # missing category
        ],
    )
    def test_malformed_structured_output_is_502(
        self,
        monkeypatch: pytest.MonkeyPatch,
        task: str,
        raw: str,
    ):
        responses = {task: raw}
        if task in (TASK_EVIDENCE, TASK_SUPPORT):
            responses.setdefault(TASK_GENERATION, _GROUNDED_JSON)
        _patch_retrieval(monkeypatch, (_candidate(1), _candidate(2)))
        _patch_provider(monkeypatch, ScriptedProvider(responses))

        with pytest.raises(GenerationFailedError) as excinfo:
            run_agent_turn(None, question=QUESTION)
        assert excinfo.value.status_code == 502
        assert excinfo.value.code == "GENERATION_FAILED"

    def test_support_category_mismatch_is_502(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """supported=true but category='exceeds_evidence' contradicts —
        malformed, never resolved in the model's favor (§3 signal D)."""
        _patch_retrieval(monkeypatch, (_candidate(1), _candidate(2)))
        _patch_provider(
            monkeypatch,
            ScriptedProvider(
                {
                    TASK_GENERATION: _GROUNDED_JSON,
                    TASK_SUPPORT: json.dumps(
                        {"supported": True, "category": "exceeds_evidence"}
                    ),
                }
            ),
        )
        with pytest.raises(GenerationFailedError):
            run_agent_turn(None, question=QUESTION)


# ---------------------------------------------------------------------------
# Determinism + gates only ever more conservative (§2, §3)
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_error_never_becomes_a_decision_state(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """A failing provider must not surface as unsupported, uncertain
        or guard — the customer gets a typed ERROR envelope instead."""
        _patch_retrieval(monkeypatch, (_candidate(1),))
        _patch_provider(monkeypatch, ScriptedProvider(LLMProviderError("boom")))

        with pytest.raises(LLMUnavailableError):
            run_agent_turn(None, question=QUESTION)

    def test_llm_verdict_cannot_resurrect_a_failed_gate(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """The model says 'sufficient' — the relevance gate already
        failed, so the turn stays UNCERTAIN and the verdict call never
        happens: gates run first and can only be more conservative."""
        _patch_retrieval(monkeypatch, (_candidate(1, similarity=0.01),))
        provider = ScriptedProvider(
            {TASK_EVIDENCE: json.dumps({"verdict": "sufficient", "conflicting_refs": []})}
        )
        _patch_provider(monkeypatch, provider)

        decision = run_agent_turn(None, question=QUESTION)

        assert decision.kind == DECISION_UNCERTAIN
        assert decision.category == CATEGORY_WEAK_RELEVANCE
        assert provider.calls_for(TASK_EVIDENCE) == []
        assert provider.generation_calls() == []

    def test_same_request_twice_yields_identical_decisions(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        def run() -> tuple:
            _patch_retrieval(monkeypatch, (_candidate(1), _candidate(2)))
            _patch_provider(
                monkeypatch, ScriptedProvider({TASK_GENERATION: _GROUNDED_JSON})
            )
            return run_agent_turn(None, question=QUESTION)

        first, second = run(), run()
        assert first.kind == second.kind
        assert first.text == second.text
        assert first.category == second.category
        assert [item.ref for item in first.cited] == [
            item.ref for item in second.cited
        ]

# ---------------------------------------------------------------------------
# 8b-4: small talk — typed greeting, one LLM call, no retrieval
# ---------------------------------------------------------------------------


class TestGreeting:
    """Greetings and pleasantries are conversation, not support questions:
    the application replies with the fixed GREETING_TEXT plus topic
    suggestions. The model never writes the reply, nothing is retrieved,
    and no escalation is attached (it is not a dead end)."""

    def test_small_talk_returns_typed_greeting(self, monkeypatch: pytest.MonkeyPatch):
        _patch_retrieval(monkeypatch, (_candidate(1),))  # would poison a retrieval
        provider = ScriptedProvider(
            {
                TASK_ASSESSMENT: json.dumps(
                    {
                        "ambiguous": False,
                        "clarification": "",
                        "options": [],
                        "small_talk": True,
                    }
                )
            }
        )
        _patch_provider(monkeypatch, provider)

        decision = run_agent_turn(None, question="how are you?")

        assert decision.kind == DECISION_GREETING
        assert decision.text == GREETING_TEXT
        assert decision.category == "small_talk"
        assert decision.escalation_offer is None
        assert decision.options == (
            "How do I reset my password?",
            "When am I billed?",
            "How do I invite my team?",
        )
        # Exactly one LLM call (assessment) — no retrieval, no generation.
        assert _tasks(provider) == [TASK_ASSESSMENT]

    def test_small_talk_with_payload_is_rejected(self, monkeypatch: pytest.MonkeyPatch):
        """A small-talk flag plus any decision payload is malformed model
        output — 502, never repaired, never shown."""
        from app.core.exceptions import GenerationFailedError

        _patch_retrieval(monkeypatch, (_candidate(1),))
        provider = ScriptedProvider(
            {
                TASK_ASSESSMENT: json.dumps(
                    {
                        "ambiguous": True,
                        "clarification": "Is this about signing in or billing?",
                        "options": ["Signing in", "Billing"],
                        "small_talk": True,
                    }
                )
            }
        )
        _patch_provider(monkeypatch, provider)

        with pytest.raises(GenerationFailedError):
            run_agent_turn(None, question=QUESTION)


# ---------------------------------------------------------------------------
# 8b-2: spelling-corrected search_query from call #1 feeds the coverage gate
# ---------------------------------------------------------------------------


class TestSearchQueryCorrection:
    """The assessment's spelling-corrected search_query (8b-2) feeds the
    deterministic coverage gate — raw token matching cannot survive
    misspelled input — while RETRIEVAL keeps the raw question: the
    embedding model is typo-robust and prefers natural sentences
    (measured live). Empty/absent correction falls back to the raw
    question (stub assessments, older prompt versions)."""

    @staticmethod
    def _team_candidates() -> tuple:
        return (
            _candidate(
                1,
                doc_title="Team Management",
                section_title="Invite your team",
                content=(
                    "Workspace owners can invite team members "
                    "by email from the team settings page."
                ),
            ),
        )

    @staticmethod
    def _patch_recording_retrieval(
        monkeypatch: pytest.MonkeyPatch,
        queries: list[str],
        candidates: tuple | None = None,
    ) -> None:
        from app.services.retrieval_service import RetrievalResult

        class RecordingRetrievalService:
            def __init__(self, db, provider=None):
                self.db = db

            def retrieve(self, query: str, **kwargs) -> RetrievalResult:
                queries.append(query)
                return RetrievalResult(
                    embedding_model="fake",
                    limit=5,
                    include_challenge_fixtures=False,
                    min_cosine_similarity=0.0,
                    candidates=candidates if candidates is not None else (_candidate(1),),
                )

        monkeypatch.setattr(
            "app.services.agent_service.RetrievalService",
            RecordingRetrievalService,
        )

    def test_retrieval_keeps_raw_question_and_coverage_uses_correction(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """Typos reach retrieval untouched (embeddings cope), while the
        coverage gate runs on the corrected tokens — so the turn grounds
        instead of dying at partial_coverage."""
        queries: list[str] = []
        self._patch_recording_retrieval(
            monkeypatch, queries, candidates=self._team_candidates()
        )
        provider = ScriptedProvider(
            {
                TASK_ASSESSMENT: json.dumps(
                    {
                        "ambiguous": False,
                        "clarification": "",
                        "options": [],
                        "search_query": "invite team members",
                    }
                ),
                TASK_GENERATION: _GROUNDED_JSON,
            }
        )
        _patch_provider(monkeypatch, provider)

        decision = run_agent_turn(None, question="hw do i invte my tem?")

        assert decision.kind == DECISION_GROUNDED
        assert queries == ["hw do i invte my tem?"]

    def test_coverage_gate_still_fails_without_correction(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """Without the correction, the misspelled question cannot pass the
        deterministic coverage gate — proving the correction is what
        rescues the turn (and that the gate stays conservative)."""
        self._patch_recording_retrieval(
            monkeypatch, [], candidates=self._team_candidates()
        )
        _patch_provider(
            monkeypatch, ScriptedProvider({TASK_GENERATION: _GROUNDED_JSON})
        )

        decision = run_agent_turn(None, question="hw do i invte my tem?")

        assert decision.kind == DECISION_UNCERTAIN
        assert decision.category == CATEGORY_PARTIAL_COVERAGE

    def test_clean_question_falls_back_to_raw_query(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """No correction emitted (stub assessments, older prompts) — the
        raw question drives both retrieval and the gate, exactly as before
        8b-2."""
        queries: list[str] = []
        self._patch_recording_retrieval(monkeypatch, queries)
        _patch_provider(
            monkeypatch, ScriptedProvider({TASK_GENERATION: _GROUNDED_JSON})
        )

        decision = run_agent_turn(None, question=QUESTION)

        assert decision.kind == DECISION_GROUNDED
        assert queries == [QUESTION]
