"""Shared test harness for the Phase 8B decision pipeline.

The automated suite never needs an NVIDIA key or network: evidence and
the LLM provider are injected by monkeypatching exactly the two seams
the pipeline exposes — `agent_service.RetrievalService` (controlled
evidence) and `agent_service.get_llm_provider` (task-scripted
completions).

Task routing (Phase 8B): every decision stage issues its own completion
call, so the scripted provider answers per task. Tests script ONLY the
stage they exercise; all other stages return deterministic defaults that
behave like the happy path (clear question / sufficient evidence /
supported answer).
"""

from __future__ import annotations

import json

import pytest

from app.llm.base import (
    TASK_ASSESSMENT,
    TASK_EVIDENCE,
    TASK_GENERATION,
    TASK_SUPPORT,
    CompletionRequest,
    LLMProvider,
)
from app.services.retrieval_service import RetrievalCandidate, RetrievalResult

QUESTION = "How do I reset my password?"

# Deterministic defaults for tasks a test does not script.
_DEFAULT_ASSESSMENT = json.dumps(
    {"ambiguous": False, "clarification": "", "options": []}
)
_DEFAULT_EVIDENCE = json.dumps(
    {"verdict": "sufficient", "conflicting_refs": []}
)
_DEFAULT_SUPPORT = json.dumps({"supported": True, "category": "supported"})
# No scripted generation → the model honestly declines to ground (this is
# also the Q2 `citation_ids: []` behavior); tests that reach generation
# script it explicitly.
_DEFAULT_GENERATION = json.dumps(
    {"answer": "The supplied documentation does not cover this.", "citation_ids": []}
)

DEFAULT_RESPONSES = {
    TASK_ASSESSMENT: _DEFAULT_ASSESSMENT,
    TASK_EVIDENCE: _DEFAULT_EVIDENCE,
    TASK_SUPPORT: _DEFAULT_SUPPORT,
    TASK_GENERATION: _DEFAULT_GENERATION,
}


class ScriptedProvider(LLMProvider):
    """Task-routed scripted completions; records every request.

    Forms:
    - `ScriptedProvider(str)`        → the string is the GENERATION
      response (the 8A pattern); every other task returns its default.
    - `ScriptedProvider({task: r})`  → per-task responses; unscripted
      tasks fall back to the defaults. A value may be an Exception,
      raised for that task only.
    - `ScriptedProvider(Exception)`  → raised for EVERY task.
    """

    def __init__(self, raw: str | Exception | dict):
        self._raw = raw
        self.calls: list[CompletionRequest] = []

    @property
    def model_name(self) -> str:
        return "scripted-test-model"

    def complete(self, request: CompletionRequest) -> str:
        self.calls.append(request)
        if isinstance(self._raw, Exception):
            raise self._raw
        if isinstance(self._raw, dict):
            response = self._raw.get(request.task, DEFAULT_RESPONSES[request.task])
            if isinstance(response, Exception):
                raise response
            return response
        if request.task == TASK_GENERATION:
            return self._raw
        return DEFAULT_RESPONSES[request.task]

    def generation_calls(self) -> list[CompletionRequest]:
        return [r for r in self.calls if r.task == TASK_GENERATION]

    def calls_for(self, task: str) -> list[CompletionRequest]:
        return [r for r in self.calls if r.task == task]


def _candidate(
    n: int,
    *,
    doc_id: str = "doc-password-help",
    doc_title: str = "Password Help",
    section_id: str = "reset-password",
    section_title: str = "Resetting your password",
    content: str = (
        "You can reset your password from the login page by selecting "
        "Forgot Password. A reset link is emailed to your account address."
    ),
    similarity: float = 0.9,
) -> RetrievalCandidate:
    """A realistic approved-scope retrieval candidate (internal ids included)."""
    return RetrievalCandidate(
        chunk_id=f"chunk-{n:04d}",
        document_id=doc_id,
        document_title=doc_title,
        section_id=section_id,
        section_title=section_title,
        chunk_index=n,
        content=content,
        knowledge_status="approved",
        source="docs",
        cosine_distance=1.0 - similarity,
        cosine_similarity=similarity,
    )


def _patch_retrieval(
    monkeypatch: pytest.MonkeyPatch,
    candidates: tuple[RetrievalCandidate, ...],
    *,
    error: Exception | None = None,
) -> None:
    """Replace the pipeline's retrieval seam with controlled evidence."""

    class FakeRetrievalService:
        def __init__(self, db, provider=None):
            self.db = db

        def retrieve(self, query: str, **kwargs) -> RetrievalResult:
            if error is not None:
                raise error
            return RetrievalResult(
                embedding_model="fake",
                limit=5,
                include_challenge_fixtures=False,
                min_cosine_similarity=0.0,
                candidates=candidates,
            )

    monkeypatch.setattr(
        "app.services.agent_service.RetrievalService", FakeRetrievalService
    )


def _patch_provider(
    monkeypatch: pytest.MonkeyPatch, provider: LLMProvider | Exception
) -> None:
    def factory(settings=None):
        if isinstance(provider, Exception):
            raise provider
        return provider

    monkeypatch.setattr("app.services.agent_service.get_llm_provider", factory)
