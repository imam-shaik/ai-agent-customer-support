"""Deterministic test-only embedding provider (Phase 7 §16).

Isolated from production configuration: the factory refuses this provider
unless ENVIRONMENT=testing. No network, no API keys, fully deterministic
— the automated suite runs offline while still exercising real SQL
ranking, status filtering and cache invalidation.

What it is NOT: a semantic model. It hashes word unigrams + bigrams into
`dimensions` buckets and L2-normalizes, so cosine similarity equals
shared-vocabulary mass. That verifies retrieval *plumbing* with varied
query wording; true paraphrase generalization is verified by the
live-provider smoke test (credentials required), never faked here.
"""

from __future__ import annotations

import hashlib
import math
import re

from app.embeddings.base import (
    EmbeddingProvider,
    EmbeddingProviderError,
    validate_batch,
)

_TOKEN_RE = re.compile(r"[a-z0-9']+")


class FakeEmbeddingProvider(EmbeddingProvider):
    """Hashed bag-of-words + bigrams, L2-normalized, deterministic."""

    def __init__(self, *, dimensions: int = 1024) -> None:
        if dimensions < 8:
            raise EmbeddingProviderError("fake provider requires dimensions >= 8")
        self._dimensions = dimensions

    @property
    def model_name(self) -> str:
        return "fake-lexical-hash-v1"

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def _embed_one(self, text: str) -> list[float]:
        tokens = _TOKEN_RE.findall(text.lower())
        features = tokens + [f"{a} {b}" for a, b in zip(tokens, tokens[1:])]
        vector = [0.0] * self._dimensions
        for feature in features:
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest, "big") % self._dimensions
            vector[bucket] += 1.0
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0.0:
            # A zero vector would make cosine undefined — never emit one.
            vector[0] = 1.0
            return vector
        return [value / norm for value in vector]

    def embed_text(self, text: str) -> list[float]:
        return self._embed_one(text)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        vectors = [self._embed_one(text) for text in texts]
        validate_batch(
            texts,
            vectors,
            expected_dimensions=self._dimensions,
            model_name=self.model_name,
        )
        return vectors
