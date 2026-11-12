"""Deterministic stub LLM (development + tests) — Phase 8B task-aware.

NOT a language model: it answers each of the four narrow decision tasks
with deterministic lexical heuristics so the FULL agent pipeline runs
without network access or API keys:

    assessment  → vague-question heuristic → canned clarification
    evidence    → always "sufficient" (the stub never claims conflict —
                  conflict behavior is proven by scripted verdicts in tests)
    generation  → lexical overlap with the question, quoting the top match
    support     → lexical check: does the answer's vocabulary come from
                  the question + evidence?

Honest limitations (documented in the Phase 8B report):
- it cannot prove semantic understanding; real-model quality is verified
  only by the live smoke (credentials required, skipped honestly);
- its ambiguity heuristic is a regex over common vague phrasings, not
  language understanding;
- its support check is lexical: paraphrases that swap vocabulary would
  false-fail — the real judge is the live model.

Contract:
- cites only refs whose evidence shares significant words with the question
- returns citation_ids: [] when nothing matches (→ typed uncertain state)
- same request → byte-identical response
"""

from __future__ import annotations

import json
import re

from app.core.text import significant_words
from app.llm.base import (
    TASK_ASSESSMENT,
    TASK_EVIDENCE,
    TASK_GENERATION,
    TASK_SUPPORT,
    CompletionRequest,
    EvidenceRef,
    LLMProvider,
)

# Vague phrasings the deterministic stand-in treats as materially
# ambiguous (Phase 8B §4). Explicitly NOT exhaustive — a real model
# judges language; this only keeps dev/test turns honest.
_VAGUE_PATTERNS = (
    re.compile(r"\bisn'?t working\b", re.IGNORECASE),
    re.compile(r"\bis not working\b", re.IGNORECASE),
    re.compile(r"\bbroken\b", re.IGNORECASE),
    re.compile(r"\bsomething wrong\b", re.IGNORECASE),
    re.compile(r"\b(?:an?\s+)?issue\b", re.IGNORECASE),
    re.compile(r"\b(?:a\s+)?problem\b", re.IGNORECASE),
)

# The one canned routing question (validated by the app: exactly one "?",
# 10–300 chars, ends with "?", no internal ids/secret phrases).
_CANNED_CLARIFICATION = (
    "Could you tell me what you're trying to do — signing in, managing "
    "billing, or using a specific feature?"
)
_CANNED_OPTIONS = ("Signing in", "Managing billing", "Using a specific feature")

# Small talk (8b-4, 8b-7): short greeting/identity messages get the same
# small_talk classification as the live model, so demo mode behaves
# identically — including filler greetings ("ok hi", 8b-7). Mirrors the
# agent's deterministic screen (full match, same 40-char cap): a real
# question that merely STARTS with "hi" must still be answered.
_GREETING_PATTERN = re.compile(
    r"^\s*(?:(?:hi|hello|hey|yo|there|ok|okay|thanks|thank\s+you|thankyou|bye|goodbye|"
    r"good\s+(?:morning|afternoon|evening))\b[\s!.?,:-]*)+$",
    re.IGNORECASE,
)
_GREETING_META_PATTERN = re.compile(
    r"^\s*(?:how\s+are\s+you|who\s+are\s+you|what\s+can\s+you\s+do)\s*[?.!]*\s*$",
    re.IGNORECASE,
)
_GREETING_MAX_CHARS = 40

# Framing word the stub's own answer template introduces ("According to …");
# allowed by the support check so template chrome never fails an answer
# that is otherwise quoted from evidence.
_TEMPLATE_WORDS = frozenset({"according"})

# Support-check threshold: share of the answer's material vocabulary that
# must come from question + evidence. 0.9 tolerates a few framing words
# while rejecting answers built from other material.
_SUPPORT_RATIO = 0.9


def _snippet(text: str, limit: int = 400) -> str:
    content = " ".join(text.split())
    if len(content) <= limit:
        return content
    return content[:limit].rsplit(" ", 1)[0] + "…"


class StubLLMProvider(LLMProvider):
    """Deterministic lexical stand-in for the real chat model."""

    @property
    def model_name(self) -> str:
        return "stub-deterministic-v1"

    def complete(self, request: CompletionRequest) -> str:
        if request.task == TASK_ASSESSMENT:
            return self._assess(request.question)
        if request.task == TASK_EVIDENCE:
            # Never claims "conflicting": the stub has no semantic model of
            # disagreement (scripted verdicts prove conflict in tests).
            return json.dumps({"verdict": "sufficient", "conflicting_refs": []})
        if request.task == TASK_SUPPORT:
            return self._support(request)
        return self._generate(request)

    # --- call #1: material ambiguity (regex heuristic, deterministic) ---

    def _assess(self, question: str) -> str:
        trimmed = (question or "").strip()
        if (
            len(trimmed) <= _GREETING_MAX_CHARS
            and (
                _GREETING_PATTERN.fullmatch(trimmed)
                or _GREETING_META_PATTERN.fullmatch(trimmed)
            )
        ):
            return json.dumps(
                {"ambiguous": False, "clarification": "", "options": [], "small_talk": True}
            )
        ambiguous = any(pattern.search(question) for pattern in _VAGUE_PATTERNS)
        if not ambiguous:
            return json.dumps(
                {"ambiguous": False, "clarification": "", "options": []}
            )
        return json.dumps(
            {
                "ambiguous": True,
                "clarification": _CANNED_CLARIFICATION,
                "options": list(_CANNED_OPTIONS),
            }
        )

    # --- call #4: lexical support check over question + evidence ---

    def _support(self, request: CompletionRequest) -> str:
        answer = request.candidate_answer or ""
        answer_words = significant_words(answer)
        if not answer_words:
            # Nothing material to check (vacuously supported).
            return json.dumps({"supported": True, "category": "supported"})
        allowed = set(_TEMPLATE_WORDS) | significant_words(request.question)
        for item in request.evidence:
            allowed |= significant_words(item.content)
            allowed |= significant_words(item.document_title)
            allowed |= significant_words(item.section_title)
        covered = len(answer_words & allowed)
        ratio = covered / len(answer_words)
        if ratio >= _SUPPORT_RATIO:
            return json.dumps({"supported": True, "category": "supported"})
        return json.dumps(
            {"supported": False, "category": "exceeds_evidence"}
        )

    # --- call #3: the Phase 8A lexical generator (behavior preserved) ---

    def _generate(self, request: CompletionRequest) -> str:
        question_words = significant_words(request.question)
        cited: list[EvidenceRef] = []
        for item in request.evidence:
            if question_words & significant_words(item.content):
                cited.append(item)

        if not question_words or not cited:
            # Nothing in the evidence shares vocabulary with the question:
            # an honest "cannot ground" — never an invented answer.
            return json.dumps(
                {
                    "answer": "The supplied documentation does not cover this.",
                    "citation_ids": [],
                }
            )

        top = cited[0]
        answer = (
            f"According to {top.document_title} ({top.section_title}): "
            f"{_snippet(top.content)}"
        )
        return json.dumps(
            {"answer": answer, "citation_ids": [item.ref for item in cited]}
        )
