"""OpenAI-compatible chat completions over HTTP (default: NVIDIA AI Foundation).

Built on the existing `httpx` dependency instead of a vendor SDK — same
discipline as the Phase 7 embedding client: one POST to
`{base_url}/chat/completions`, so the endpoint can be swapped (hosted
NVIDIA today, a self-hosted NIM or any OpenAI-compatible server later)
purely by configuration.

Endpoint facts (documented schema, verified for meta/llama-3.3-70b-instruct):
- `max_tokens` is capped at 4096 — enforced by config validation;
- there is NO documented `response_format` field (`additionalProperties:
  false`), so JSON output is requested through instructions and, more
  importantly, enforced by strict application-side validation. Provider
  schema support ≠ application trust (§11).
"""

from __future__ import annotations

import httpx

from app.llm.base import CompletionRequest, LLMProvider, LLMProviderError
from app.llm.prompting import render_user_prompt


class NVIDIAChatProvider(LLMProvider):
    """`POST /v1/chat/completions` client (OpenAI request/response shape)."""

    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        api_key: str,
        timeout_seconds: float,
        temperature: float,
        max_tokens: int,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise LLMProviderError("LLM API key is not configured")
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens
        # The key lives only in the header of this client — never logged,
        # never stored, never sent anywhere else.
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
            transport=transport,
            headers={"Authorization": f"Bearer {api_key}"},
        )

    @property
    def model_name(self) -> str:
        return self._model

    def complete(self, request: CompletionRequest) -> str:
        # The agent core renders the untrusted user message for every task
        # (Phase 8B); fall back to the generation renderer only when a
        # caller constructed the request without one (direct unit use).
        user_prompt = request.user_prompt or render_user_prompt(
            request.question, request.evidence
        )
        try:
            response = self._client.post(
                "/chat/completions",
                json={
                    "model": self._model,
                    "messages": [
                        # Trusted instructions first (schema requires system
                        # to be the very first message when present).
                        {"role": "system", "content": request.system_prompt},
                        # Untrusted question + evidence as data.
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": self._temperature,
                    "max_tokens": self._max_tokens,
                    "stream": False,
                },
            )
        except httpx.HTTPError as exc:
            # Exception type only — httpx messages can embed URL/headers.
            raise LLMProviderError(
                f"LLM request failed ({type(exc).__name__})"
            ) from exc

        if response.status_code != 200:
            # Provider-generated body (truncated); our key only ever lives
            # in the request header, never in the body.
            detail = (response.text or "").strip()[:300]
            raise LLMProviderError(
                f"LLM API returned HTTP {response.status_code}: {detail}"
            )

        try:
            choice = response.json()["choices"][0]
            content = choice["message"]["content"]
            finish_reason = choice.get("finish_reason")
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise LLMProviderError(
                "LLM API returned an unexpected payload shape"
            ) from exc

        if finish_reason == "length":
            # A truncated response cannot be trusted to hold valid JSON.
            raise LLMProviderError(
                "LLM response was truncated at llm_max_completion_tokens"
            )
        if not isinstance(content, str) or not content.strip():
            raise LLMProviderError("LLM API returned an empty completion")
        return content
