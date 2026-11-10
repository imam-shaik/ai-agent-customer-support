"""Bounded conversation context + working retrieval query (Phase 8B §4).

Two deterministic helpers, no LLM involvement:

- `build_context` selects the LAST N messages before the current one,
  each truncated — a hard bound on prompt growth (default 6 × 500 chars
  ≈ 3 KB) no matter how long the conversation gets. The full history is
  never concatenated into a prompt.
- `compose_retrieval_query` connects a clarification follow-up to the
  question that triggered it: when the immediately preceding assistant
  reply was `clarifying`, the working query is exactly two pieces
  (triggering user message + current message), each capped at 400 chars,
  so turn-2 retrieval sees turn-1's context too.

Roles are preserved and every context entry is rendered into the
UNTRUSTED section of the user message only (§7 structural boundary) —
old customer text can never become trusted instructions.
"""

from __future__ import annotations

from dataclasses import dataclass

# Caps for the two-piece clarification working query (§4).
_QUERY_PIECE_MAX_CHARS = 400


@dataclass(frozen=True)
class ContextTurn:
    """One bounded history entry: role label + truncated content."""

    role: str  # "user" | "assistant"
    content: str


def build_context(
    messages,
    *,
    max_messages: int,
    max_chars: int,
) -> tuple[ContextTurn, ...]:
    """The last `max_messages` messages, each truncated to `max_chars`.

    `messages` is the history BEFORE the current user message (tail-reuse
    rows excluded by the caller). Chronological order is preserved.
    """
    if max_messages < 1 or max_chars < 1:
        raise ValueError("context bounds must be positive")
    selected = list(messages)[-max_messages:]
    turns: list[ContextTurn] = []
    for message in selected:
        role = getattr(message, "role", None)
        content = getattr(message, "content", None)
        if role not in ("user", "assistant") or not isinstance(content, str):
            continue  # never render anything that is not a plain chat turn
        turns.append(ContextTurn(role=role, content=content[:max_chars]))
    return tuple(turns)


def compose_retrieval_query(messages, current: str) -> str:
    """Working query for retrieval AND the coverage gate (§4).

    Follow-up to a clarification: `triggering_user_message + " " + current`
    (each piece ≤ 400 chars). Otherwise: the current message alone.
    The raw current question stays the question of record in the reply.
    """
    current = (current or "").strip()
    history = list(messages)
    if not history:
        return current

    last = history[-1]
    reply = getattr(last, "reply", None)
    if getattr(last, "role", None) != "assistant" or not isinstance(reply, dict):
        return current
    if reply.get("kind") != "clarifying":
        return current

    # The triggering user message is the nearest `user` turn before the
    # clarifying assistant reply.
    triggering = ""
    for message in reversed(history[:-1]):
        if getattr(message, "role", None) == "user":
            triggering = (getattr(message, "content", "") or "").strip()
            break
    if not triggering:
        return current

    piece_a = triggering[:_QUERY_PIECE_MAX_CHARS]
    piece_b = current[:_QUERY_PIECE_MAX_CHARS]
    return f"{piece_a} {piece_b}".strip()
