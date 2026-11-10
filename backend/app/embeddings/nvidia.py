"""OpenAI-compatible embeddings over HTTP (default: NVIDIA AI Foundation).

Deliberately built on the existing `httpx` dependency instead of a vendor
SDK: one POST to `{base_url}/embeddings`, so the endpoint can be swapped
(hosted NVIDIA today, a self-hosted NIM or any OpenAI-compatible server
later) purely by configuration.
"""

from __future__ import annotations

import httpx

from app.embeddings.base import (
    EmbeddingProvider,
    EmbeddingProviderError,
    validate_batch,
)


class OpenAICompatibleEmbeddingProvider(EmbeddingProvider):
    """`POST /v1/embeddings` client (OpenAI request/response shape)."""

    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        api_key: str,
        dimensions: int,
        timeout_seconds: float,
        batch_size: int,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise EmbeddingProviderError("embedding API key is not configured")
        self._model = model
        self._dimensions = dimensions
        self._batch_size = batch_size
        # The key lives only in the header of this client — it is never
        # logged, never stored in the database, never sent elsewhere.
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
            transport=transport,
            headers={"Authorization": f"Bearer {api_key}"},
        )

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed_text(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if len(texts) > self._batch_size:
            raise EmbeddingProviderError(
                f"batch of {len(texts)} texts exceeds configured "
                f"embedding_batch_size={self._batch_size}"
            )
        try:
            response = self._client.post(
                "/embeddings",
                json={
                    "model": self._model,
                    "input": list(texts),
                    "encoding_format": "float",
                },
            )
        except httpx.HTTPError as exc:
            # Exception type only — httpx messages can embed the URL and
            # headers; we never log or re-raise raw request detail.
            raise EmbeddingProviderError(
                f"embedding request failed ({type(exc).__name__})"
            ) from exc

        if response.status_code != 200:
            # Provider-generated body (truncated) is safe to surface; our
            # API key is only ever in the request header, never the body.
            detail = (response.text or "").strip()[:300]
            raise EmbeddingProviderError(
                f"embedding API returned HTTP {response.status_code}: {detail}"
            )

        try:
            rows = sorted(response.json()["data"], key=lambda row: row.get("index", 0))
            vectors = [row["embedding"] for row in rows]
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise EmbeddingProviderError(
                "embedding API returned an unexpected payload shape"
            ) from exc

        validate_batch(
            texts,
            vectors,
            expected_dimensions=self._dimensions,
            model_name=self._model,
        )
        return vectors
