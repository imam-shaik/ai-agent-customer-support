"""Embedding provider tests (Phase 7 §16).

Split by capability:
- The deterministic fake provider: identity, determinism, normalization —
  it must be a stable test double, never a semantic claim.
- The OpenAI-compatible provider: exercised fully through httpx's
  MockTransport, so HTTP behavior (ordering, error mapping, truncation,
  dimension validation) is covered WITHOUT network access or keys.
- The factory guards: fake refused outside testing, real refused without
  a key, dimension mismatches refused before any data is written.
"""

import math
import json

import httpx
import pytest

from app.core.config import Settings
from app.embeddings import (
    EmbeddingProviderError,
    ensure_configured_dimensions,
    get_embedding_provider,
)
from app.embeddings.base import validate_batch
from app.embeddings.fake import FakeEmbeddingProvider
from app.embeddings.nvidia import OpenAICompatibleEmbeddingProvider

MODEL = "nvidia/nv-embedqa-e5-v5"
KEY = "nvapi-unit-test-key"


# --- fake provider ---------------------------------------------------------


class TestFakeProvider:
    def test_same_text_is_deterministic(self):
        provider = FakeEmbeddingProvider(dimensions=1024)
        first = provider.embed_text("password reset link")
        second = provider.embed_text("password reset link")
        assert first == second
        assert len(first) == 1024

    def test_different_text_is_different(self):
        provider = FakeEmbeddingProvider(dimensions=1024)
        assert provider.embed_text("alpha") != provider.embed_text("beta")

    def test_vectors_are_unit_norm(self):
        provider = FakeEmbeddingProvider(dimensions=1024)
        for text in ("password reset", "billing invoice", "   ", "!!!"):
            vector = provider.embed_text(text)
            norm = math.sqrt(sum(value * value for value in vector))
            assert abs(norm - 1.0) < 1e-9, f"not unit norm for {text!r}"

    def test_no_token_text_never_emits_zero_vector(self):
        # A zero vector would make cosine distance undefined in pgvector.
        provider = FakeEmbeddingProvider(dimensions=64)
        vector = provider.embed_text("??? !!!")
        assert any(value != 0.0 for value in vector)

    def test_batch_matches_single_calls_in_order(self):
        provider = FakeEmbeddingProvider(dimensions=1024)
        vectors = provider.embed_batch(["first text", "second text"])
        assert vectors[0] == provider.embed_text("first text")
        assert vectors[1] == provider.embed_text("second text")

    def test_model_name_is_stable_identity(self):
        assert FakeEmbeddingProvider().model_name == "fake-lexical-hash-v1"


# --- factory guards --------------------------------------------------------


class TestFactoryGuards:
    def test_fake_refused_outside_testing(self):
        settings = Settings(environment="development", embedding_provider="fake")
        with pytest.raises(EmbeddingProviderError, match="testing"):
            get_embedding_provider(settings)

    def test_fake_allowed_in_testing(self):
        settings = Settings(environment="testing", embedding_provider="fake")
        provider = get_embedding_provider(settings)
        assert isinstance(provider, FakeEmbeddingProvider)

    def test_real_provider_refused_without_api_key(self):
        settings = Settings(embedding_provider="nvidia", embedding_api_key=None)
        with pytest.raises(EmbeddingProviderError, match="EMBEDDING_API_KEY"):
            get_embedding_provider(settings)

    def test_unknown_provider_rejected(self):
        settings = Settings(embedding_provider="made-up-vendor")
        with pytest.raises(EmbeddingProviderError, match="made-up-vendor"):
            get_embedding_provider(settings)


class TestDimensionGuards:
    def test_settings_must_match_schema_dimension(self):
        settings = Settings(embedding_dimensions=512)
        provider = FakeEmbeddingProvider(dimensions=512)
        with pytest.raises(EmbeddingProviderError, match="migration"):
            ensure_configured_dimensions(settings, provider)

    def test_provider_must_match_settings_dimension(self):
        settings = Settings(embedding_dimensions=4096)
        provider = FakeEmbeddingProvider(dimensions=512)
        with pytest.raises(EmbeddingProviderError, match="512"):
            ensure_configured_dimensions(settings, provider)

    def test_matching_dimensions_pass(self):
        settings = Settings(embedding_dimensions=4096)
        ensure_configured_dimensions(settings, FakeEmbeddingProvider(dimensions=4096))


class TestBatchValidation:
    def test_count_mismatch_rejected(self):
        with pytest.raises(EmbeddingProviderError, match="1 vectors"):
            validate_batch(
                ["a", "b"],
                [[0.0] * 8],
                expected_dimensions=8,
                model_name="m",
            )

    def test_width_mismatch_rejected(self):
        with pytest.raises(EmbeddingProviderError, match="4 dimensions"):
            validate_batch(
                ["a"],
                [[0.0] * 4],
                expected_dimensions=8,
                model_name="m",
            )


# --- OpenAI-compatible provider (MockTransport, no network) ---------------


def _provider(
    transport: httpx.BaseTransport,
    *,
    dimensions: int = 1024,
    batch_size: int = 4,
) -> OpenAICompatibleEmbeddingProvider:
    return OpenAICompatibleEmbeddingProvider(
        model=MODEL,
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=KEY,
        dimensions=dimensions,
        timeout_seconds=5.0,
        batch_size=batch_size,
        transport=transport,
    )


class TestOpenAICompatibleProvider:
    def test_missing_api_key_rejected_at_construction(self):
        with pytest.raises(EmbeddingProviderError, match="API key"):
            OpenAICompatibleEmbeddingProvider(
                model=MODEL,
                base_url="https://example.invalid/v1",
                api_key="",
                dimensions=1024,
                timeout_seconds=5.0,
                batch_size=4,
            )

    def test_success_sorts_by_index_and_returns_in_input_order(self):
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["authorization"] = request.headers.get("Authorization", "")
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"index": 1, "embedding": [0.0] * 1024},
                        {"index": 0, "embedding": [1.0] * 1024},
                    ]
                },
            )

        provider = _provider(httpx.MockTransport(handler))
        vectors = provider.embed_batch(["first", "second"])
        assert vectors[0] == [1.0] * 1024
        assert vectors[1] == [0.0] * 1024
        # The key travels only in the request header.
        assert seen["authorization"] == f"Bearer {KEY}"

    def test_embed_text_single_path(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, json={"data": [{"index": 0, "embedding": [0.5] * 1024}]}
            )

        provider = _provider(httpx.MockTransport(handler))
        assert provider.embed_text("hello") == [0.5] * 1024
        assert provider.model_name == MODEL
        assert provider.dimensions == 1024

    def test_asymmetric_roles_wire_input_type_per_call(self):
        """Queries and passages carry their configured input_type — the
        asymmetric models require it, and mixing the roles degrades them."""
        seen: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content.decode("utf-8"))
            seen.append(payload)
            count = len(payload["input"])
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"index": i, "embedding": [0.5] * 1024} for i in range(count)
                    ]
                },
            )

        provider = OpenAICompatibleEmbeddingProvider(
            model=MODEL,
            base_url="https://integrate.api.nvidia.com/v1",
            api_key=KEY,
            dimensions=1024,
            timeout_seconds=5.0,
            batch_size=4,
            query_input_type="query",
            passage_input_type="passage",
            transport=httpx.MockTransport(handler),
        )
        provider.embed_text("How do I reset my password?")
        provider.embed_batch(["chunk one", "chunk two"])
        assert [payload.get("input_type") for payload in seen] == [
            "query",
            "passage",
        ]

    def test_symmetric_model_sends_no_input_type(self):
        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(json.loads(request.content.decode("utf-8")))
            return httpx.Response(
                200, json={"data": [{"index": 0, "embedding": [0.5] * 1024}]}
            )

        seen: list[dict] = []
        provider = _provider(httpx.MockTransport(handler))
        provider.embed_text("hello")
        assert seen[0].get("input_type") is None

    def test_http_error_maps_to_provider_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="internal server error")

        provider = _provider(httpx.MockTransport(handler))
        with pytest.raises(EmbeddingProviderError, match="HTTP 500"):
            provider.embed_text("hello")

    def test_error_body_is_truncated(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, text="x" * 5000)

        provider = _provider(httpx.MockTransport(handler))
        with pytest.raises(EmbeddingProviderError) as excinfo:
            provider.embed_text("hello")
        assert len(str(excinfo.value)) < 400

    def test_malformed_payload_rejected(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"unexpected": True})

        provider = _provider(httpx.MockTransport(handler))
        with pytest.raises(EmbeddingProviderError, match="payload"):
            provider.embed_text("hello")

    def test_wrong_dimension_rejected(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, json={"data": [{"index": 0, "embedding": [0.0] * 64}]}
            )

        provider = _provider(httpx.MockTransport(handler))
        with pytest.raises(EmbeddingProviderError, match="64 dimensions"):
            provider.embed_text("hello")

    def test_missing_vector_rejected(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.0] * 1024}]})

        provider = _provider(httpx.MockTransport(handler))
        with pytest.raises(EmbeddingProviderError, match="1 vectors"):
            provider.embed_batch(["one", "two"])

    def test_transport_failure_never_leaks_key_or_detail(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("boom: secret endpoint detail", request=request)

        provider = _provider(httpx.MockTransport(handler))
        with pytest.raises(EmbeddingProviderError) as excinfo:
            provider.embed_text("hello")
        message = str(excinfo.value)
        assert "(ConnectError)" in message
        assert KEY not in message
        assert "secret endpoint detail" not in message

    def test_oversized_batch_rejected_before_request(self):
        calls: list = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return httpx.Response(200, json={"data": []})

        provider = _provider(httpx.MockTransport(handler), batch_size=1)
        with pytest.raises(EmbeddingProviderError, match="batch"):
            provider.embed_batch(["a", "b"])
        assert calls == []  # rejected before any HTTP traffic
