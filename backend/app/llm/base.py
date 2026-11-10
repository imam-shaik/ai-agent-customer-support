"""LLM provider boundary (Phase 8A §3).

A deliberately small abstraction — two methods' worth of surface:

    ChatService/agent core  →  LLMProvider.complete(request)  →  raw text
                               ├── StubLLMProvider   (dev/test, deterministic)
                               └── NVIDIAChatProvider (real OpenAI-compatible HTTP)

The agent core — not the provider — owns instructions, prompt rendering,
JSON parsing, schema validation and citation validation. The provider is
transport: it turns a request into text and back. Provider-level schema
support would never be trusted anyway (§11): the application re-validates
every response regardless.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

# The four narrow LLM tasks of the Phase 8B decision machine (§2). The
# task never travels as free text — it is an app-side constant used for
# instruction selection and logging; the transport ignores it entirely.
TASK_ASSESSMENT = "assessment"      # call #1: material ambiguity?
TASK_EVIDENCE = "evidence"          # call #2: sufficiency/conflict verdict
TASK_GENERATION = "generation"      # call #3: the grounded answer (8A)
TASK_SUPPORT = "support"            # call #4: narrow answer-support judge


class LLMProviderError(Exception):
    """Provider-level failure: credentials, transport, unexpected envelope.

    Carries a safe, client-presentable message only — never API keys,
    never raw request detail (mirrors EmbeddingProviderError).
    """


@dataclass(frozen=True)
class EvidenceRef:
    """One retrieved chunk, referenced turn-locally as E1, E2, ...

    The `ref` is the ONLY identifier the LLM may cite; `chunk_id` and
    `document_id` exist purely for application-side mapping and are never
    rendered into a prompt (§8).
    """

    ref: str
    chunk_id: str
    document_id: str
    section_id: str
    document_title: str
    section_title: str
    content: str


@dataclass(frozen=True)
class CompletionRequest:
    """Everything a provider may see — rendered by the agent core.

    `system_prompt` is TRUSTED application instructions (built from the
    task's instruction block). `question`, `evidence`, `context`,
    `candidate_answer` and `user_prompt` are UNTRUSTED data (§6 trust
    boundary) — no combination of them ever enters the system message.

    `user_prompt` is the fully rendered untrusted user message; when the
    agent core sets it, providers use it verbatim (every task renders its
    own untrusted payload, and rendering must happen in exactly one
    place). `question`/`evidence` remain for compatibility and logging.
    """

    system_prompt: str
    question: str
    evidence: tuple[EvidenceRef, ...] = ()
    task: str = TASK_GENERATION
    # Bounded conversation context (role, content) — untrusted, rendered
    # only into the user message (Phase 8B §4).
    context: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    # Candidate answer for the support check (call #4) — untrusted.
    candidate_answer: str | None = None
    # Pre-rendered untrusted user message (authoritative when provided).
    user_prompt: str | None = None


class LLMProvider(ABC):
    @property
    @abstractmethod
    def model_name(self) -> str:
        """Configured model id (for logs and observability)."""

    @abstractmethod
    def complete(self, request: CompletionRequest) -> str:
        """Return the raw completion text (expected: exactly one JSON object)."""
