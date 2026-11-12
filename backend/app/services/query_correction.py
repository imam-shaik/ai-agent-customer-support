"""Deterministic demo-mode query correction — spelling tolerance (8b-7).

WHY IT EXISTS: live mode tolerates typos twice over — the assessment
model emits a spelling-corrected search_query (8b-2) that feeds the
coverage gate, and the real embedding is typo-robust so retrieval copes
with the raw question. Demo mode has neither: the lexical fake embedding
and the stub generator's token overlap both fail on a single misspelling
("when am i billled?" dead-ended in weak_relevance while the correctly
spelled question grounded — observed 2026-11-12). This module gives demo
mode the same tolerance with a deterministic, conservative rule:
NO LLM call, no network, no semantic guessing.

THE RULE (per token, deterministic):
- tokens shorter than 4 characters are never corrected ("i", "ok", "hi"
  and other filler stay untouched);
- a token that appears in the corpus vocabulary is kept as-is;
- otherwise the nearest vocabulary word with the SAME first letter is
  considered, within a small edit-distance budget (<=1 for tokens of
  length 4-5, <=2 for length >=6);
- the correction is applied only when that nearest word is UNIQUE — a
  tie means the intended word is ambiguous, so the token is kept
  as-is. Conservative over clever: a kept typo degrades exactly as it
  did before this module existed; a wrong correction could silently
  change the question's meaning.

The vocabulary comes from the retrievable corpus itself (READY +
approved chunks), so corrections always map onto words the knowledge
base actually uses. The customer's persisted message and the raw
question of record are never rewritten — only the working text that
feeds demo retrieval, the coverage gate and the stub generator.
"""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Document, DocumentChunk
from app.services.retrieval_service import NORMAL_RETRIEVAL_STATUSES

# Same token shape as app.core.text: lowercase word characters only.
_TOKEN_RE = re.compile(r"[a-z0-9']+")

# Correction is for real words only; greetings and filler stay as typed.
_MIN_TOKEN_CHARS = 4

# The longest slip a typo-tolerance budget should absorb: one edit for
# short words, two for long ones (doubled letters, swapped pair).
_DISTANCE_BUDGETS = ((5, 1), (float("inf"), 2))


def corpus_vocabulary(db: Session) -> frozenset[str]:
    """Lowercased word tokens of every RETRIEVABLE chunk (READY + approved).

    Corrections can only ever map onto words the approved knowledge base
    actually uses — a typo is never "corrected" into a word the customer
    could not have asked about. Challenge fixtures and archived documents
    are excluded for the same reason retrieval excludes them.
    """
    rows = db.execute(
        select(DocumentChunk.content)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            Document.status == "READY",
            Document.knowledge_status.in_(NORMAL_RETRIEVAL_STATUSES),
        )
    ).scalars()
    vocabulary: set[str] = set()
    for content in rows:
        vocabulary.update(_TOKEN_RE.findall((content or "").lower()))
    return frozenset(vocabulary)


def correct_spelling(text: str, vocabulary: frozenset[str]) -> str:
    """Correct out-of-vocabulary tokens; everything else is verbatim.

    Pure string surgery on token boundaries — punctuation, spacing and
    untouched tokens are preserved exactly.
    """

    def _correct(match: re.Match[str]) -> str:
        token = match.group(0)
        replacement = _correct_token(token.lower(), vocabulary)
        return replacement if replacement is not None else token

    return _TOKEN_RE.sub(_correct, text or "")


def _distance_budget(token_length: int) -> int:
    for bound, budget in _DISTANCE_BUDGETS:
        if token_length <= bound:
            return budget
    return _DISTANCE_BUDGETS[-1][1]


def _correct_token(token: str, vocabulary: frozenset[str]) -> str | None:
    """The unique near-match for one token, or None to keep it as typed."""
    if len(token) < _MIN_TOKEN_CHARS or token in vocabulary:
        return None
    budget = _distance_budget(len(token))
    best: list[str] = []
    best_distance = budget + 1
    for word in vocabulary:
        # Same first letter keeps corrections anchored to the intended
        # word shape; the length gap must fit the budget at all.
        if word[0] != token[0] or abs(len(word) - len(token)) > budget:
            continue
        distance = _edit_distance(token, word, budget)
        if distance is None:
            continue
        if distance < best_distance:
            best, best_distance = [word], distance
        elif distance == best_distance:
            best.append(word)
    if len(best) != 1:
        # No near match, or an ambiguous one — never guess.
        return None
    return best[0]


def _edit_distance(a: str, b: str, limit: int) -> int | None:
    """Levenshtein distance, or None once it provably exceeds `limit`."""
    if abs(len(a) - len(b)) > limit:
        return None
    previous = list(range(len(b) + 1))
    for i, char_a in enumerate(a, start=1):
        current = [i]
        row_min = i
        for j, char_b in enumerate(b, start=1):
            cost = 0 if char_a == char_b else 1
            value = min(
                previous[j] + 1,  # deletion
                current[j - 1] + 1,  # insertion
                previous[j - 1] + cost,  # substitution / match
            )
            current.append(value)
            if value < row_min:
                row_min = value
        if row_min > limit:
            return None  # whole row already over budget — abandon
        previous = current
    return previous[-1] if previous[-1] <= limit else None
