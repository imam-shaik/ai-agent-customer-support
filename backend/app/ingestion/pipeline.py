"""Ingestion pipeline: normalization → sections → chunks (Phase 6).

Design principles:

- **Faithful normalization.** We fix structure (line endings, stray
  whitespace, repeated blank lines) but never rewrite wording —
  normalization improves structure, it must not change policy meaning.
- **Structure-aware chunking.** Chunks break on section and paragraph
  boundaries first; sentence-level splitting with overlap is a fallback
  for single oversized paragraphs. Code fences are never split.
- **Deterministic output.** The same content always produces the same
  sections, slugs, chunk order and chunk text — reprocessing is safe.
- **Provenance everywhere.** Every chunk carries its document order
  (chunk_index) and its section reference (section_id + section_title),
  so the chain answer → citation → chunk → section → document holds.

No embeddings, no LLM, no vector logic here — that is Phase 7.
"""

import hashlib
import re
from dataclasses import dataclass, field

from app.core.config import get_settings
from app.ingestion.extractors import IngestionError, get_extractor

# Version of the chunking rules below. Bump if chunk output changes
# shape so reprocessing can be recognized later.
PIPELINE_VERSION = "1"

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")


@dataclass(frozen=True)
class Section:
    """A logical document section detected from headings."""

    id: str
    title: str
    level: int
    lines: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ChunkDraft:
    """A chunk ready to persist: ordered, section-attributed, traceable."""

    chunk_index: int
    section_id: str
    section_title: str
    content: str

    @property
    def char_count(self) -> int:
        return len(self.content)


@dataclass(frozen=True)
class ProcessedDocument:
    """Full pipeline output for one document."""

    title: str
    normalized_text: str
    content_hash: str
    source_type: str
    sections: list[Section]
    chunks: list[ChunkDraft]
    pipeline_version: str = PIPELINE_VERSION


# --------------------------------------------------------------------------
# Normalization
# --------------------------------------------------------------------------

def normalize(text: str) -> str:
    """Structure-only normalization. Idempotent: normalize(x) == normalize(normalize(x)).

    - unify CRLF/CR → LF
    - strip a leading BOM
    - trim trailing whitespace per line (leading whitespace is kept —
      it is meaningful for indentation and code blocks)
    - collapse runs of 2+ blank lines to a single blank line
    - trim leading/trailing blank lines
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if text.startswith("\ufeff"):
        text = text[1:]

    out: list[str] = []
    blanks = 0
    for line in text.split("\n"):
        stripped = line.rstrip()
        if stripped == "":
            blanks += 1
            if blanks > 1:
                continue  # keep at most one consecutive blank line
        else:
            blanks = 0
        out.append(stripped)

    return "\n".join(out).strip()


def content_hash(normalized_text: str) -> str:
    """SHA-256 of the NORMALIZED text.

    Hashing the normalized form means the same document uploaded with
    different line endings or trailing whitespace is recognized as a
    duplicate. Wording changes produce a different hash.
    """
    return hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()


def slugify(title: str) -> str:
    """Deterministic section id: lowercase, non-alphanumeric runs → '-'."""
    slug = re.sub(r"[\W_]+", "-", title.lower()).strip("-")
    return slug or "section"


# --------------------------------------------------------------------------
# Section detection
# --------------------------------------------------------------------------

def detect_sections(normalized: str, doc_title: str) -> list[Section]:
    """Split into sections at Markdown headings.

    Rules (documented fallback strategy):
    - The FIRST heading, if it is an H1, is the document title — it does
      not create a section (the title belongs to the Document row).
    - Every other heading (any level, including later H1s) starts a new
      section. Sub-headings are their own sections — finer citations.
    - Lines inside code fences never count as headings.
    - No headings at all → one logical section with id "main" (plain
      text documents). Non-empty text before the first section heading
      becomes an "introduction" section.
    - Duplicate heading titles get a deterministic "-2", "-3" suffix.
    - Section names come only from the document itself — never invented.
    """
    lines = normalized.split("\n")
    preamble: list[str] = []
    sections: list[Section] = []
    current: Section | None = None
    in_fence = False
    title_seen = False
    used_ids: dict[str, int] = {}

    def unique_id(title: str) -> str:
        base = slugify(title)
        count = used_ids.get(base, 0) + 1
        used_ids[base] = count
        return base if count == 1 else f"{base}-{count}"

    for line in lines:
        if _FENCE_RE.match(line):
            in_fence = not in_fence

        match = None if in_fence else _HEADING_RE.match(line)
        if match:
            level = len(match.group(1))
            heading_text = match.group(2).strip()
            if not title_seen and level == 1:
                title_seen = True  # first H1 = document title, not a section
                continue
            title_seen = True
            if current is not None and any(ln.strip() for ln in current.lines):
                sections.append(current)
            current = Section(id=unique_id(heading_text), title=heading_text, level=level)
            continue

        if current is None:
            if line.strip():
                preamble.append(line)
        else:
            current.lines.append(line)

    if current is not None and any(ln.strip() for ln in current.lines):
        sections.append(current)

    if not sections:
        # No headings (or only a title): the whole document is one section.
        if preamble:
            return [Section(id="main", title=doc_title or "Document", level=0, lines=preamble)]
        return []

    if preamble:
        sections.insert(
            0, Section(id="introduction", title="Introduction", level=0, lines=preamble)
        )
    return sections


def extract_title(normalized: str, fallback: str) -> str:
    """Document title from the first H1, else the provided fallback."""
    for line in normalized.split("\n"):
        match = _HEADING_RE.match(line)
        if match and len(match.group(1)) == 1:
            return match.group(2).strip()
        if line.strip():
            break  # first non-empty line is not an H1
    return fallback


# --------------------------------------------------------------------------
# Chunking
# --------------------------------------------------------------------------

def _split_paragraphs(lines: list[str]) -> list[str]:
    """Blank-line separated paragraphs; blank lines inside code fences
    do NOT break the paragraph (fenced blocks stay whole)."""
    paragraphs: list[str] = []
    buffer: list[str] = []
    in_fence = False
    for line in lines:
        if _FENCE_RE.match(line):
            in_fence = not in_fence
        if line.strip() == "" and not in_fence:
            if buffer:
                paragraphs.append("\n".join(buffer).strip("\n"))
                buffer = []
            continue
        buffer.append(line)
    if buffer:
        paragraphs.append("\n".join(buffer).strip("\n"))
    return [p for p in paragraphs if p.strip()]


def _contains_fence(text: str) -> bool:
    return any(_FENCE_RE.match(line) for line in text.split("\n"))


def _split_oversized(text: str, max_chars: int, overlap_chars: int) -> list[str]:
    """Sentence-level split for a single paragraph that exceeds max_chars.

    Applied only when paragraph grouping cannot help (one huge paragraph).
    Overlap carries the tail of the previous piece into the next so a
    sentence spanning the boundary stays retrievable.
    """
    pieces: list[str] = []
    current = ""
    for sentence in _SENTENCE_SPLIT_RE.split(text):
        candidate = f"{current} {sentence}".strip() if current else sentence
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            pieces.append(current)
            current = ""
        # A single sentence longer than the limit: hard-split it (the
        # uniform overlap pass below handles the boundaries).
        while len(sentence) > max_chars:
            pieces.append(sentence[:max_chars])
            sentence = sentence[max_chars:]
        current = sentence
    if current:
        pieces.append(current)

    if overlap_chars > 0 and len(pieces) > 1:
        overlapped = [pieces[0]]
        for previous, following in zip(pieces, pieces[1:]):
            tail = previous[-overlap_chars:].lstrip()
            overlapped.append(f"{tail} {following}".strip() if tail else following)
        pieces = overlapped
    return pieces


def chunk_sections(
    sections: list[Section], max_chars: int, overlap_chars: int
) -> list[ChunkDraft]:
    """Structure-aware chunking, in document order.

    Strategy:
    1. Within a section, group whole paragraphs greedily up to max_chars.
    2. A single paragraph over max_chars is split at sentence boundaries
       with overlap — unless it contains a code fence, which stays whole
       (splitting code would destroy meaning; one oversized code chunk is
       the lesser evil and code blocks in this corpus are small).
    3. Chunks are numbered globally across the document (0..n-1) so order
       is deterministic and queryable.

    No overlap between paragraph-grouped chunks: paragraphs are already
    coherent units, and blind overlap would duplicate policy text.
    """
    drafts: list[ChunkDraft] = []
    index = 0

    for section in sections:
        paragraphs = _split_paragraphs(section.lines)
        if not paragraphs:
            continue  # a heading with no body has nothing to retrieve

        groups: list[str] = []
        current = ""
        for paragraph in paragraphs:
            candidate = f"{current}\n\n{paragraph}" if current else paragraph
            if current and len(candidate) > max_chars:
                groups.append(current)
                current = paragraph
            else:
                current = candidate
        if current:
            groups.append(current)

        pieces: list[str] = []
        for group in groups:
            if len(group) <= max_chars or _contains_fence(group):
                pieces.append(group)  # oversized non-code groups stay atomic too
            else:
                pieces.extend(_split_oversized(group, max_chars, overlap_chars))

        for piece in pieces:
            if not piece.strip():
                continue
            drafts.append(
                ChunkDraft(
                    chunk_index=index,
                    section_id=section.id,
                    section_title=section.title,
                    content=piece,
                )
            )
            index += 1

    return drafts


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------

def run_pipeline(raw_content: str, source_type: str, doc_title: str) -> ProcessedDocument:
    """Extract → normalize → detect sections → chunk.

    Raises IngestionError with a safe reason on any failure; callers
    mark the document FAILED — never READY.
    """
    settings = get_settings()

    result = get_extractor(source_type).extract(raw_content.encode("utf-8"))
    if not result.ok:
        raise IngestionError(result.reason or "The document could not be read.")

    normalized = normalize(result.text)
    if not normalized:
        raise IngestionError("The document contains no meaningful text.")

    title = extract_title(normalized, doc_title)
    sections = detect_sections(normalized, title)
    chunks = chunk_sections(
        sections, settings.chunk_max_chars, settings.chunk_overlap_chars
    )
    if not chunks:
        raise IngestionError("The document produced no retrievable content.")

    return ProcessedDocument(
        title=title,
        normalized_text=normalized,
        content_hash=content_hash(normalized),
        source_type=result.source_type,
        sections=sections,
        chunks=chunks,
    )
