"""Embedding provider boundary (Phase 7 §4).

Indexing and retrieval depend only on this interface, so the provider can
be swapped later (different vendor, self-hosted NIM) without touching the
retrieval service, database logic, or API routes. Failures are always
raised as EmbeddingProviderError — never masked with fake vectors.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class EmbeddingProviderError(RuntimeError):
    """Provider misconfiguration, call failure, or malformed output.

    Raised loudly on purpose: a failed embed call must never become a
    silently-searchable fake vector or a chunk that pretends to be indexed.
    """


class EmbeddingProvider(ABC):
    """Small boundary: text in, vectors out. Nothing else."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Model id stored on every vector (identity + invalidation)."""

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Vector dimensionality this provider guarantees."""

    @abstractmethod
    def embed_text(self, text: str) -> list[float]:
        """Embed one text verbatim.

        Role prefixes (E5's "query: " / "passage: ") are applied by the
        CALLERS — indexing passes passages, retrieval passes the query —
        so the provider stays model-agnostic.
        """

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch in one request; result order matches input order."""


def validate_batch(
    texts: list[str],
    vectors: list[list[float]],
    *,
    expected_dimensions: int,
    model_name: str,
) -> None:
    """Guard against providers returning wrong-shaped or missing vectors."""
    if len(vectors) != len(texts):
        raise EmbeddingProviderError(
            f"embedding provider {model_name} returned {len(vectors)} vectors "
            f"for {len(texts)} inputs"
        )
    for position, vector in enumerate(vectors):
        if len(vector) != expected_dimensions:
            raise EmbeddingProviderError(
                f"embedding provider {model_name} returned {len(vector)} dimensions "
                f"at position {position}, expected {expected_dimensions}"
            )
