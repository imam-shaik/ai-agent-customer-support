"""LLM provider factory (Phase 8A §3–4).

Provider selection is configuration-only:
- `nvidia` (default): real OpenAI-compatible endpoint; requires NVIDIA_API_KEY.
  Without a key, chat raises a clear LLMProviderError → explicit 503
  instead of silently falling back to canned/fake answers.
- `stub`: deterministic generator, reachable when ENVIRONMENT=testing
  or through the explicit local Demo mode (refused in production). Demo
  keeps live keys and vectors untouched.

The LLM provider and the embedding provider (app/embeddings) remain
SEPARATE logical components: same vendor and possibly the same key, but
either can move to another provider without touching the other.
"""

from __future__ import annotations

from app.llm.base import (
    CompletionRequest,
    EvidenceRef,
    LLMProvider,
    LLMProviderError,
)


def get_llm_provider(settings=None) -> LLMProvider:
    """Build the configured provider. Late imports keep import cycles away."""
    from app.core.config import get_settings
    from app.llm.nvidia import NVIDIAChatProvider
    from app.llm.stub import StubLLMProvider

    settings = settings or get_settings()

    # Explicit local Demo mode: deterministic stub generator, no network
    # and no API key. It never rewrites the configured live provider and
    # is refused in production by provider_mode_service.
    from app.services.provider_mode_service import is_demo_mode

    if is_demo_mode():
        return StubLLMProvider()

    kind = settings.llm_provider

    if kind == "stub":
        # Test-suite configuration only; Demo mode is handled above.
        if settings.environment != "testing":
            raise LLMProviderError(
                "LLM_PROVIDER=stub is only allowed when ENVIRONMENT=testing — "
                "configure a real provider (LLM_PROVIDER=nvidia + NVIDIA_API_KEY) "
                "instead of serving fabricated answers"
            )
        return StubLLMProvider()

    if kind == "nvidia":
        if not settings.nvidia_api_key:
            raise LLMProviderError(
                "NVIDIA_API_KEY is not configured; set it to enable real LLM "
                "generation (see backend/.env.example). Chat refuses to "
                "fabricate answers without it."
            )
        return NVIDIAChatProvider(
            model=settings.llm_model,
            base_url=settings.llm_base_url,
            api_key=settings.nvidia_api_key,
            timeout_seconds=settings.llm_timeout_seconds,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_completion_tokens,
        )

    raise LLMProviderError(
        f"unknown LLM_PROVIDER {kind!r} (expected 'stub' or 'nvidia')"
    )


__all__ = [
    "CompletionRequest",
    "EvidenceRef",
    "LLMProvider",
    "LLMProviderError",
    "get_llm_provider",
]
