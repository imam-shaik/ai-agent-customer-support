"""Text extraction boundary (Phase 6).

All file-reading/decoding logic lives here — never in API routes or
services. An extractor turns raw bytes into text plus safe metadata.
Future formats (PDF) plug in behind the same surface without touching
the pipeline:

    Document bytes ──► get_extractor(source_type) ──► ExtractionResult

Failures raise IngestionError with a safe, client-presentable reason;
no stack traces or byte-level detail ever reaches the API response.
"""

from dataclasses import dataclass

# Bytes above which the leading region is sniffed for binary content.
_SNIFF_LEN = 8192
# Share of control characters (excluding tab/newline/carriage return)
# above which content is considered binary rather than text.
_MAX_CONTROL_RATIO = 0.02


class IngestionError(Exception):
    """Pipeline failure carrying a safe reason (never internal detail)."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class ExtractionResult:
    """Outcome of extraction: text plus safe processing metadata."""

    text: str
    source_type: str
    ok: bool
    reason: str | None = None


BINARY_REASON = "The document appears to be binary data, not text."


def storage_failure_reason(text: str) -> str | None:
    """Safe reason when text cannot be stored in a text column at all.

    PostgreSQL text columns reject NUL (0x00) bytes anywhere in the value
    (SQLite tolerated them). The check therefore runs BEFORE the row
    insert — with the same client-facing reason the byte-level extractor
    sniff produces — so a NUL-byte upload is persisted as a FAILED
    document instead of crashing the INSERT.
    """
    if "\x00" in text:
        return BINARY_REASON
    return None


def infer_source_type(source: str | None) -> str | None:
    """Infer the extractor from a filename/extension. None = unknown.

    The extension is only a hint: the content is still sniffed and
    decoded by the extractor, so a renamed binary file is rejected.
    """
    if not source:
        return None
    name = source.strip().lower().split("?")[0]
    if name.endswith((".md", ".markdown")):
        return "markdown"
    if name.endswith((".txt", ".text", ".textfile")):
        return "text"
    return None


class _BaseExtractor:
    """Shared UTF-8 decode + binary sniffing for line-oriented formats."""

    source_type = "text"

    def extract(self, data: bytes) -> ExtractionResult:
        if not data:
            return ExtractionResult("", self.source_type, False, "The document is empty.")

        head = data[:_SNIFF_LEN]
        if b"\x00" in head:
            return ExtractionResult(
                "", self.source_type, False,
                "The document appears to be binary data, not text.",
            )
        control = sum(1 for byte in head if byte < 32 and byte not in (9, 10, 13))
        if control / len(head) > _MAX_CONTROL_RATIO:
            return ExtractionResult(
                "", self.source_type, False,
                "The document contains control characters and is not readable text.",
            )

        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            return ExtractionResult(
                "", self.source_type, False,
                "The document is not valid UTF-8 encoded text.",
            )

        text = text.lstrip("\ufeff")  # strip BOM if present
        return ExtractionResult(text, self.source_type, True)


class MarkdownExtractor(_BaseExtractor):
    """Markdown documents. Kept separate so Markdown-specific handling
    (front matter, heading validation, …) has a home later without
    touching shared decoding."""

    source_type = "markdown"


class TextExtractor(_BaseExtractor):
    """Plain text documents (single logical section downstream)."""

    source_type = "text"


_EXTRACTORS = {
    "markdown": MarkdownExtractor,
    "text": TextExtractor,
}

SUPPORTED_SOURCE_TYPES = tuple(_EXTRACTORS)


def get_extractor(source_type: str) -> _BaseExtractor:
    try:
        return _EXTRACTORS[source_type]()
    except KeyError:
        raise IngestionError(f"Unsupported document type: {source_type}.") from None
