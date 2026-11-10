"""Evidence context construction (Phase 8A §8–9).

Turns ranked retrieval candidates into the controlled evidence set shown
to the LLM:

    candidates (ranked) → explicit count/size limits → E1, E2, … → prompt

- Turn-local references only: `E1` means nothing outside this call, so the
  model can never cite a database id it happened to see or invent one.
- Explicit limits from config (§9): `LLM_MAX_EVIDENCE` caps the item count
  (default 5 = retrieval top-k), `LLM_EVIDENCE_MAX_CHARS` caps each item's
  text (default 1200 = chunk size). The prompt never grows unbounded.
- Internal identifiers (chunk_id/document_id) ride along in the dataclass
  for application-side citation mapping — they are NEVER rendered.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.llm.base import EvidenceRef


def build_evidence(
    candidates: Iterable,
    *,
    max_items: int,
    max_chars: int,
) -> tuple[EvidenceRef, ...]:
    refs: list[EvidenceRef] = []
    for candidate in candidates:
        if len(refs) >= max_items:
            break
        content = (candidate.content or "").strip()
        if not content:
            continue  # an empty chunk can support nothing
        if len(content) > max_chars:
            content = content[:max_chars].rsplit(" ", 1)[0] + " …"
        refs.append(
            EvidenceRef(
                ref=f"E{len(refs) + 1}",  # dense, gap-free numbering
                chunk_id=candidate.chunk_id,
                document_id=candidate.document_id,
                section_id=candidate.section_id,
                document_title=candidate.document_title,
                section_title=candidate.section_title,
                content=content,
            )
        )
    return tuple(refs)
