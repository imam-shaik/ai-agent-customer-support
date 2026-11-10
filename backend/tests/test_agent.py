"""Phase 8B agent decision tests (evolved from Phase 8A §19 scenarios).

The automated suite never needs an NVIDIA key or network: evidence and
the LLM provider are injected by monkeypatching exactly the two seams
the pipeline exposes — `agent_service.RetrievalService` (controlled
evidence) and `agent_service.get_llm_provider` (task-scripted
completions). Shared helpers live in `agent_harness.py`.

8A → 8B evolutions (documented in the Phase 8B report §H):
- `generate_grounded_answer` → `run_agent_turn` (the full state machine);
- OUTCOME_* → DECISION_*;
- the empty-evidence test asserts ZERO GENERATION calls (the mandated
  pre-retrieval assessment call still runs — §17's intent, never asking
  the model to invent an answer, is what is enforced);
- model-declines (`citation_ids: []`) now maps to UNCERTAIN/model_declined
  (decision Q2), never to unsupported;
- trusted/untrusted separation is asserted for EVERY task request;
- turn-local citation fixtures carry vocabulary that satisfies the
  deterministic coverage gate.

Coverage map (Phase 8B prompt §18 + 8A §19):
    valid grounded answer + citations ......... TestGroundedGeneration
    cites E1 and E2 correctly ................. TestGroundedGeneration
    invented E99 → rejected ................... TestMalformedOutput
    malformed JSON → rejected safely .......... TestMalformedOutput
    empty evidence → no generation call ....... TestNoEvidenceAndFailures
    provider unavailable → safe error ......... TestNoEvidenceAndFailures
    customer message persisted ................ test_chat.py (persistence)
    failed decision persists no answer ........ TestChatFailureSafety
    retry does not duplicate the message ...... TestChatFailureSafety
    only this turn's evidence is citable ...... TestTurnLocalCitations
"""

import json

import pytest
from fastapi.testclient import TestClient

from app.core.exceptions import (
    EmbeddingUnavailableError,
    GenerationFailedError,
    LLMUnavailableError,
)
from app.embeddings import EmbeddingProviderError
from app.llm import LLMProviderError
from app.llm.base import TASK_ASSESSMENT, TASK_GENERATION, TASK_SUPPORT
from app.llm.prompting import (
    ESCALATION_OFFER_TEXT,
    FALLBACK_UNSUPPORTED_TEXT,
    UNCERTAIN_TEXT,
    build_system_prompt,
)
from app.services.agent_service import (
    CATEGORY_MODEL_DECLINED,
    DECISION_GROUNDED,
    DECISION_UNCERTAIN,
    DECISION_UNSUPPORTED,
    run_agent_turn,
)
from tests.agent_harness import (
    QUESTION,
    ScriptedProvider,
    _candidate,
    _patch_provider,
    _patch_retrieval,
)


# ---------------------------------------------------------------------------
# grounded generation (8A behavior preserved inside the 8B machine)
# ---------------------------------------------------------------------------


class TestGroundedGeneration:
    def test_valid_grounded_answer_with_valid_citation(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        _patch_retrieval(monkeypatch, (_candidate(1), _candidate(2)))
        provider = ScriptedProvider(
            json.dumps({"answer": "Reset it from the login page.", "citation_ids": ["E1"]})
        )
        _patch_provider(monkeypatch, provider)

        decision = run_agent_turn(None, question=QUESTION)

        assert decision.kind == DECISION_GROUNDED
        assert decision.text == "Reset it from the login page."
        assert [item.ref for item in decision.cited] == ["E1"]
        # E1 maps back to THE REAL chunk (the LLM never sees this id):
        assert decision.cited[0].chunk_id == "chunk-0001"
        assert decision.escalation_offer is None  # grounded is no dead end

    def test_llm_cites_e1_and_e2_correctly(self, monkeypatch: pytest.MonkeyPatch):
        _patch_retrieval(monkeypatch, (_candidate(1), _candidate(2)))
        provider = ScriptedProvider(
            json.dumps(
                {
                    "answer": "Both sources describe the reset flow.",
                    "citation_ids": ["E1", "E2"],
                }
            )
        )
        _patch_provider(monkeypatch, provider)

        decision = run_agent_turn(None, question=QUESTION)

        assert decision.kind == DECISION_GROUNDED
        assert [item.ref for item in decision.cited] == ["E1", "E2"]
        assert [item.chunk_id for item in decision.cited] == [
            "chunk-0001",
            "chunk-0002",
        ]

    def test_duplicate_citations_are_deduplicated(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        _patch_retrieval(monkeypatch, (_candidate(1), _candidate(2)))
        provider = ScriptedProvider(
            json.dumps(
                {"answer": "Answer.", "citation_ids": ["E2", "E2", "E1"]}
            )
        )
        _patch_provider(monkeypatch, provider)

        decision = run_agent_turn(None, question=QUESTION)

        assert [item.ref for item in decision.cited] == ["E2", "E1"]
        assert len(decision.cited) == 2

    def test_request_keeps_trusted_and_untrusted_separate(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """§6/§7: every task's system prompt is the trusted instructions,
        byte-identical across requests; question/evidence/context travel
        ONLY in the untrusted user message."""
        evidence_content = _candidate(1).content
        _patch_retrieval(monkeypatch, (_candidate(1),))
        provider = ScriptedProvider(
            json.dumps({"answer": "Answer.", "citation_ids": ["E1"]})
        )
        _patch_provider(monkeypatch, provider)

        run_agent_turn(None, question=QUESTION)

        # One request per stage (single evidence item → verdict skipped):
        # assessment → generation → support.
        assert {r.task for r in provider.calls} == {
            TASK_ASSESSMENT,
            TASK_GENERATION,
            TASK_SUPPORT,
        }
        for request in provider.calls:
            # Trusted side: the task's fixed instructions, nothing else.
            assert request.system_prompt == build_system_prompt(request.task)
            assert QUESTION not in request.system_prompt
            assert evidence_content not in request.system_prompt
            # Untrusted side: rendered as data in the user message.
            assert request.user_prompt is not None
            assert request.user_prompt != request.system_prompt

        generation = provider.calls_for(TASK_GENERATION)[0]
        assert generation.system_prompt == build_system_prompt()
        assert generation.question == QUESTION
        assert [item.ref for item in generation.evidence] == ["E1"]
        # Internal ids ride along for app-side mapping only:
        assert generation.evidence[0].chunk_id == "chunk-0001"
        assert QUESTION in generation.user_prompt
        assert evidence_content in generation.user_prompt


# ---------------------------------------------------------------------------
# malformed output + invalid citations → rejected, never repaired (§12, §13)
# ---------------------------------------------------------------------------


class TestMalformedOutput:
    def test_prose_response_is_rejected(self, monkeypatch: pytest.MonkeyPatch):
        _patch_retrieval(monkeypatch, (_candidate(1),))
        _patch_provider(monkeypatch, ScriptedProvider("Sure! You can reset it."))
        with pytest.raises(GenerationFailedError) as excinfo:
            run_agent_turn(None, question=QUESTION)
        assert excinfo.value.status_code == 502
        assert excinfo.value.code == "GENERATION_FAILED"

    def test_non_object_json_is_rejected(self, monkeypatch: pytest.MonkeyPatch):
        _patch_retrieval(monkeypatch, (_candidate(1),))
        _patch_provider(monkeypatch, ScriptedProvider('["E1", "E2"]'))
        with pytest.raises(GenerationFailedError):
            run_agent_turn(None, question=QUESTION)

    def test_missing_required_field_is_rejected(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        # citation_ids MISSING is a contract violation — not "no citations".
        _patch_retrieval(monkeypatch, (_candidate(1),))
        _patch_provider(monkeypatch, ScriptedProvider(json.dumps({"answer": "x"})))
        with pytest.raises(GenerationFailedError):
            run_agent_turn(None, question=QUESTION)

    def test_extra_field_is_rejected(self, monkeypatch: pytest.MonkeyPatch):
        _patch_retrieval(monkeypatch, (_candidate(1),))
        _patch_provider(
            monkeypatch,
            ScriptedProvider(
                json.dumps(
                    {"answer": "x", "citation_ids": ["E1"], "confidence": 0.9}
                )
            ),
        )
        with pytest.raises(GenerationFailedError):
            run_agent_turn(None, question=QUESTION)

    def test_empty_answer_is_rejected(self, monkeypatch: pytest.MonkeyPatch):
        _patch_retrieval(monkeypatch, (_candidate(1),))
        _patch_provider(
            monkeypatch,
            ScriptedProvider(json.dumps({"answer": "", "citation_ids": ["E1"]})),
        )
        with pytest.raises(GenerationFailedError):
            run_agent_turn(None, question=QUESTION)

    def test_invented_citation_is_rejected(self, monkeypatch: pytest.MonkeyPatch):
        _patch_retrieval(monkeypatch, (_candidate(1), _candidate(2)))
        provider = ScriptedProvider(
            json.dumps({"answer": "x", "citation_ids": ["E99"]})
        )
        _patch_provider(monkeypatch, provider)

        with pytest.raises(GenerationFailedError) as excinfo:
            run_agent_turn(None, question=QUESTION)

        assert excinfo.value.status_code == 502
        # The provider WAS consulted — the failure is citation validation.
        assert len(provider.generation_calls()) == 1

    def test_database_ids_are_never_citable(self, monkeypatch: pytest.MonkeyPatch):
        """A model 'guessing' an internal id gains nothing: it is not in the
        turn-local map and is rejected like any invented reference."""
        _patch_retrieval(monkeypatch, (_candidate(1),))
        _patch_provider(
            monkeypatch,
            ScriptedProvider(
                json.dumps(
                    {"answer": "x", "citation_ids": ["chunk-0001", "doc-password-help"]}
                )
            ),
        )
        with pytest.raises(GenerationFailedError):
            run_agent_turn(None, question=QUESTION)

    def test_rejection_message_is_safe(self, monkeypatch: pytest.MonkeyPatch):
        """No stack traces, no provider detail, no internal ids (§18)."""
        _patch_retrieval(monkeypatch, (_candidate(1),))
        _patch_provider(
            monkeypatch,
            ScriptedProvider(json.dumps({"answer": "x", "citation_ids": ["E99"]})),
        )
        with pytest.raises(GenerationFailedError) as excinfo:
            run_agent_turn(None, question=QUESTION)
        message = str(excinfo.value)
        assert "E99" not in message
        assert "chunk" not in message.lower()

    def test_malformed_first_attempt_is_retried_once(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """A transient malformed first answer is re-asked ONCE (the live
        ~7% failure mode), then validated like any other answer. The
        retry is bounded: consecutive failures still raise 502, which
        the static-garbage tests above already exercise."""

        class FirstAttemptMalformed(ScriptedProvider):
            """First generation call returns malformed JSON; every later
            call behaves exactly like the scripted provider."""

            def __init__(self, raw: str) -> None:
                super().__init__(raw)
                self._first_generation = True

            def complete(self, request):
                if request.task == TASK_GENERATION and self._first_generation:
                    self._first_generation = False
                    self.calls.append(request)
                    return "total garbage, not JSON"
                return super().complete(request)

        _patch_retrieval(monkeypatch, (_candidate(1), _candidate(2)))
        provider = FirstAttemptMalformed(
            json.dumps(
                {"answer": "Reset it from the login page.", "citation_ids": ["E1"]}
            )
        )
        _patch_provider(monkeypatch, provider)

        decision = run_agent_turn(None, question=QUESTION)

        assert decision.kind == DECISION_GROUNDED
        assert decision.text == "Reset it from the login page."
        # malformed first attempt + one retry (identical prompt)
        assert len(provider.generation_calls()) == 2


# ---------------------------------------------------------------------------
# no evidence / provider failure (§17, §18)
# ---------------------------------------------------------------------------


class TestNoEvidenceAndFailures:
    def test_empty_evidence_never_calls_the_generation_llm(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """§17: without evidence the model is never asked to invent an
        answer. 8B flow evolution: the pre-retrieval question assessment
        (call #1) still runs — the enforced boundary is ZERO GENERATION
        calls, the typed fallback, and no model wording."""
        _patch_retrieval(monkeypatch, ())
        provider = ScriptedProvider("I would have invented an answer!")
        _patch_provider(monkeypatch, provider)

        decision = run_agent_turn(None, question=QUESTION)

        assert decision.kind == DECISION_UNSUPPORTED
        assert decision.text == FALLBACK_UNSUPPORTED_TEXT
        assert decision.cited == ()
        assert decision.evidence == ()
        # The answer-generating task was NEVER invoked:
        assert provider.generation_calls() == []
        # ...while the assessment stage ran (documented evolution):
        assert provider.calls_for(TASK_ASSESSMENT)
        # Dead end → the escalation offer is attached (§11):
        assert decision.escalation_offer

    def test_provider_construction_failure_maps_to_503(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        _patch_retrieval(monkeypatch, (_candidate(1),))
        _patch_provider(
            monkeypatch,
            LLMProviderError("NVIDIA_API_KEY is not configured"),
        )
        with pytest.raises(LLMUnavailableError) as excinfo:
            run_agent_turn(None, question=QUESTION)
        assert excinfo.value.status_code == 503
        assert excinfo.value.code == "LLM_PROVIDER_UNAVAILABLE"

    def test_provider_transport_failure_maps_to_503(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        _patch_retrieval(monkeypatch, (_candidate(1),))
        _patch_provider(monkeypatch, ScriptedProvider(LLMProviderError("timeout")))
        with pytest.raises(LLMUnavailableError):
            run_agent_turn(None, question=QUESTION)

    def test_embedding_failure_maps_to_503(self, monkeypatch: pytest.MonkeyPatch):
        _patch_retrieval(
            monkeypatch,
            (),
            error=EmbeddingProviderError("embedding API key is not configured"),
        )
        with pytest.raises(EmbeddingUnavailableError) as excinfo:
            run_agent_turn(None, question=QUESTION)
        assert excinfo.value.status_code == 503
        assert excinfo.value.code == "EMBEDDING_PROVIDER_UNAVAILABLE"

    def test_model_declining_grounding_returns_typed_uncertain(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """citation_ids: [] is schema-VALID — the model saw this turn's
        evidence and declined to ground on it. Q2 decision: evidence
        existed, so this is UNCERTAIN/model_declined, never disguised as
        unsupported. The model's wording is discarded (§6)."""
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
        assert decision.evidence  # evidence was retrieved, model just declined
        assert decision.escalation_offer == ESCALATION_OFFER_TEXT


# ---------------------------------------------------------------------------
# turn-local citations (§13)
# ---------------------------------------------------------------------------


class TestTurnLocalCitations:
    def test_only_current_turn_evidence_is_citable(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        """E1 is re-issued every turn: citing 'E1' in turn 2 resolves to
        turn 2's chunk, never to a chunk from an earlier turn.
        (Fixture contents cover their questions' material words so the
        deterministic coverage gate passes — 8B evolution.)"""
        _patch_retrieval(
            monkeypatch,
            (_candidate(1, content="Turn one evidence about how to reset your password."),),
        )
        first = ScriptedProvider(
            json.dumps({"answer": "First.", "citation_ids": ["E1"]})
        )
        _patch_provider(monkeypatch, first)
        decision_one = run_agent_turn(None, question=QUESTION)
        assert decision_one.cited[0].chunk_id == "chunk-0001"

        # Turn 2: DIFFERENT evidence (a different chunk got E1).
        _patch_retrieval(
            monkeypatch,
            (
                _candidate(
                    9,
                    doc_id="doc-billing",
                    doc_title="Billing Guide",
                    section_id="invoices",
                    content="Turn two evidence about how invoices work.",
                ),
            ),
        )
        second = ScriptedProvider(
            json.dumps({"answer": "Second.", "citation_ids": ["E1"]})
        )
        _patch_provider(monkeypatch, second)
        decision_two = run_agent_turn(None, question="How do invoices work?")

        assert decision_two.kind == DECISION_GROUNDED
        assert decision_two.cited[0].chunk_id == "chunk-0009"
        assert decision_two.cited[0].document_id == "doc-billing"
        # Turn 1's citation is untouched — history is immutable evidence.
        assert decision_one.cited[0].chunk_id == "chunk-0001"


# ---------------------------------------------------------------------------
# chat-level failure safety (§18) — through the REAL endpoint
# ---------------------------------------------------------------------------


def _conversation(client: TestClient) -> str:
    return client.post("/api/v1/chat/sessions", json={}).json()["conversationId"]


class TestChatFailureSafety:
    def test_failed_generation_persists_customer_message_only(
        self, client: TestClient, db_session, monkeypatch: pytest.MonkeyPatch
    ):
        from sqlalchemy import func, select

        from app.models import Message

        _patch_retrieval(monkeypatch, (_candidate(1),))
        _patch_provider(monkeypatch, LLMProviderError("provider unreachable"))

        conversation_id = _conversation(client)
        response = client.post(
            f"/api/v1/chat/sessions/{conversation_id}/messages",
            json={"content": QUESTION},
        )

        assert response.status_code == 503
        assert response.json()["error"]["code"] == "LLM_PROVIDER_UNAVAILABLE"

        roles = db_session.scalars(
            select(Message.role).where(Message.conversation_id == conversation_id)
        ).all()
        assert roles == ["user"]  # message survived; no invalid assistant row

        assistant_count = db_session.scalar(
            select(func.count())
            .select_from(Message)
            .where(
                Message.conversation_id == conversation_id,
                Message.role == "assistant",
            )
        )
        assert assistant_count == 0

    def test_retry_after_failure_does_not_duplicate_customer_message(
        self, client: TestClient, db_session, monkeypatch: pytest.MonkeyPatch
    ):
        from sqlalchemy import select

        from app.models import Message
        from app.llm import get_llm_provider as real_factory

        # Real retrieval (real chunks, so citations satisfy FKs); only the
        # provider is scripted — first garbage, then the deterministic stub.
        _patch_provider(monkeypatch, ScriptedProvider("total garbage, not JSON"))

        conversation_id = _conversation(client)
        first = client.post(
            f"/api/v1/chat/sessions/{conversation_id}/messages",
            json={"content": QUESTION},
        )
        assert first.status_code == 502
        assert first.json()["error"]["code"] == "GENERATION_FAILED"

        # Retry with a working provider: the identical, still-unanswered
        # customer message must be REUSED, not stored twice (§18).
        _patch_provider(monkeypatch, real_factory())
        second = client.post(
            f"/api/v1/chat/sessions/{conversation_id}/messages",
            json={"content": QUESTION},
        )
        assert second.status_code == 200

        rows = list(
            db_session.scalars(
                select(Message).where(Message.conversation_id == conversation_id)
            ).all()
        )
        assert [row.role for row in rows] == ["user", "assistant"]
        user_rows = [row for row in rows if row.role == "user"]
        assert len(user_rows) == 1
        assert user_rows[0].content == QUESTION

    def test_normal_second_turn_is_not_swallowed_by_tail_reuse(
        self, client: TestClient, db_session, monkeypatch: pytest.MonkeyPatch
    ):
        """Tail-reuse only applies while the identical message is the
        UNANSWERED tail; after a successful answer the same text is a new turn."""
        from sqlalchemy import func, select

        from app.models import Message

        conversation_id = _conversation(client)
        client.post(
            f"/api/v1/chat/sessions/{conversation_id}/messages",
            json={"content": QUESTION},
        )
        client.post(
            f"/api/v1/chat/sessions/{conversation_id}/messages",
            json={"content": QUESTION},
        )

        user_count = db_session.scalar(
            select(func.count())
            .select_from(Message)
            .where(
                Message.conversation_id == conversation_id,
                Message.role == "user",
            )
        )
        assert user_count == 2


class TestGroundedPersistence:
    def test_accepted_answer_persists_provenance(
        self, client: TestClient, db_session
    ):
        from sqlalchemy import select

        from app.models import Citation, Message

        conversation_id = _conversation(client)
        response = client.post(
            f"/api/v1/chat/sessions/{conversation_id}/messages",
            json={"content": QUESTION},
        )
        body = response.json()
        assert response.status_code == 200
        assert body["assistantMessage"]["reply"]["kind"] == "grounded"

        rows = list(
            db_session.scalars(
                select(Citation).where(
                    Citation.message_id == body["assistantMessage"]["id"]
                )
            ).all()
        )
        assert len(rows) >= 1
        for citation in rows:
            assert citation.chunk_id  # exact chunk provenance (§16)
            snapshot = citation.evidence_snapshot
            assert snapshot["document_title"]
            assert snapshot["section_title"]
            assert snapshot["snippet"]

        assistant = db_session.get(Message, body["assistantMessage"]["id"])
        assert assistant.reply["kind"] == "grounded"
        assert assistant.content == body["assistantMessage"]["reply"]["text"]
