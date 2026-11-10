"""Provider-settings contracts (post-Phase-12 operator addition).

The staff dialog lets the operator paste provider keys so they no longer
have to edit `backend/.env` by hand. Security posture is unchanged:

- keys live SERVER-SIDE ONLY (in `backend/.env`, the same file the
  launcher and config already read);
- the browser submits a key once over local HTTP and never stores it
  (no localStorage, no state kept after the dialog closes);
- responses carry booleans and short masked previews (last 4 chars)
  only — never key material;
- keys are never logged.
"""

from typing import Literal

from pydantic import Field

from app.schemas.common import ApiModel


class ProviderSettingsOut(ApiModel):
    """Honest provider/status snapshot (booleans + masked keys only)."""

    environment: str
    # Effective providers: "live" = real NVIDIA providers answer;
    # "demo" = the deterministic TEST providers (ENVIRONMENT=testing only).
    provider_mode: Literal["live", "demo"]
    embedding_provider: str
    llm_provider: str
    embedding_model: str
    llm_model: str
    embedding_key_configured: bool
    llm_key_configured: bool
    embedding_key_masked: str | None = None
    llm_key_masked: str | None = None
    # What the current state means operationally (restart/index guidance).
    mode_note: str


class ProviderModeUpdate(ApiModel):
    """Demo/Live selection for the local operator workspace."""

    mode: Literal["demo", "live"]


class ProviderKeysUpdate(ApiModel):
    """Keys to persist. `None` = leave that key unchanged."""

    embedding_api_key: str | None = Field(default=None, max_length=400)
    nvidia_api_key: str | None = Field(default=None, max_length=400)


class ProviderVerifyRequest(ApiModel):
    """Keys to test against the real provider endpoint (nothing is stored)."""

    embedding_api_key: str | None = Field(default=None, max_length=400)
    nvidia_api_key: str | None = Field(default=None, max_length=400)


class ProviderVerifyItemOut(ApiModel):
    """One key's live-check result: honest ok/error, never key material."""

    ok: bool
    error: str | None = None


class ProviderVerifyOut(ApiModel):
    embedding: ProviderVerifyItemOut | None = None
    chat: ProviderVerifyItemOut | None = None
