"""Embedding provider factory (Phase 7 §4, §16).

Provider selection is configuration-only:
- `nvidia` (default): real OpenAI-compatible endpoint; requires
  EMBEDDING_API_KEY. Without a key, indexing/retrieval raise a clear
  EmbeddingProviderError instead of serving fake vectors.
- `fake`: deterministic TEST-ONLY provider, reachable exclusively when
  ENVIRONMENT=testing. There is no runtime override that can attach it
  to development or production traffic.
"""

from __future__ import annotations

from app.embeddings.base import (
    EmbeddingProvider,
    EmbeddingProviderError,
    validate_batch,
)


def get_embedding_provider(settings=None) -> EmbeddingProvider:
    """Build the configured provider. Late imports keep import cycles away."""
    from app.core.config import get_settings
    from app.embeddings.fake import FakeEmbeddingProvider
    from app.embeddings.nvidia import OpenAICompatibleEmbeddingProvider

    settings = settings or get_settings()
    kind = settings.embedding_provider

    if kind == "fake":
        # Test-suite only. ENVIRONMENT=testing is set by tests/conftest.py
        # before any import; no operator toggle exists to widen this.
        if settings.environment != "testing":
            raise EmbeddingProviderError(
                "EMBEDDING_PROVIDER=fake is only allowed when ENVIRONMENT=testing — "
                "fake embeddings must never serve real traffic"
            )
        return FakeEmbeddingProvider(dimensions=settings.embedding_dimensions)

    if kind == "nvidia":
        if not settings.embedding_api_key:
            raise EmbeddingProviderError(
                "EMBEDDING_API_KEY is not configured; set it to enable real embeddings "
                "(see backend/.env.example). Indexing and retrieval refuse to run "
                "without it rather than serving fake vectors."
            )
        return OpenAICompatibleEmbeddingProvider(
            model=settings.embedding_model,
            base_url=settings.embedding_base_url,
            api_key=settings.embedding_api_key,
            dimensions=settings.embedding_dimensions,
            timeout_seconds=settings.embedding_timeout_seconds,
            batch_size=settings.embedding_batch_size,
        )

    raise EmbeddingProviderError(
        f"unknown EMBEDDING_PROVIDER {kind!r} (expected 'nvidia' or 'fake')"
    )


def ensure_configured_dimensions(settings, provider: EmbeddingProvider) -> None:
    """Fail loudly when config, schema and provider dimensions disagree.

    The schema column is vector(2048) (migration c4f8a1d6e2b9); changing
    EMBEDDING_DIMENSIONS without a migration — or a provider returning a
    different width — must stop the run before any data is written or any
    misleading ranking is returned.
    """
    from app.models.entities import VECTOR_DIMENSIONS

    if settings.embedding_dimensions != VECTOR_DIMENSIONS:
        raise EmbeddingProviderError(
            f"EMBEDDING_DIMENSIONS={settings.embedding_dimensions} does not match the "
            f"pgvector schema vector({VECTOR_DIMENSIONS}); run a migration first"
        )
    if provider.dimensions != settings.embedding_dimensions:
        raise EmbeddingProviderError(
            f"provider {provider.model_name} produces {provider.dimensions} dimensions but "
            f"EMBEDDING_DIMENSIONS={settings.embedding_dimensions}"
        )


__all__ = [
    "EmbeddingProvider",
    "EmbeddingProviderError",
    "ensure_configured_dimensions",
    "get_embedding_provider",
    "validate_batch",
]
