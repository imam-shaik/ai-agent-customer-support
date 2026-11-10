"""Provider key management for the staff settings dialog (operator aid).

Responsibilities:
- report provider/status state honestly (booleans + masked previews only);
- persist submitted keys to `backend/.env` — the SAME file the launcher
  (`run.bat live`) and `Settings` already read, so nothing new is trusted;
- optionally verify a submitted key with one real provider call before it
  is saved, returning an honest ok/error per key.

Trust boundary (unchanged from the audit): `/admin/*` is an
unauthenticated localhost surface (documented production blocker); the
dev server binds 127.0.0.1, so only local operators reach it. Keys are
NEVER logged and NEVER returned — not even in error messages.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.core.config import get_settings
from app.core.exceptions import InvalidInputError
from app.core.logging import get_logger
from app.embeddings.nvidia import OpenAICompatibleEmbeddingProvider
from app.llm.base import TASK_GENERATION, CompletionRequest
from app.llm.nvidia import NVIDIAChatProvider
from app.schemas.provider_settings import (
    ProviderKeysUpdate,
    ProviderSettingsOut,
    ProviderVerifyItemOut,
    ProviderVerifyOut,
    ProviderVerifyRequest,
)

logger = get_logger("app.providers")

# Resolved at call time (see env_path()) so tests can point it at a temp
# file and so the path always matches the CWD-relative `.env` that
# `Settings(env_file=".env")` reads.
_ENV_FILENAME = ".env"

# NVIDIA API keys: `nvapi-` prefix + token characters. Deliberately not
# stricter than that — format is a sanity screen, the live verify call is
# the real check.
_KEY_PATTERN = re.compile(r"^nvapi-[A-Za-z0-9_\-]{16,}$")

_MASKED_PREFIX = "nvapi-…"

_MIN_VERIFY_TOKENS = 16
_VERIFY_TIMEOUT_CAP = 15.0

_MINIMAL_ENV_TEMPLATE = (
    "# Created by the staff provider-settings dialog.\n"
    "# Full option reference: backend/.env.example\n"
    "EMBEDDING_API_KEY={embedding}\n"
    "NVIDIA_API_KEY={chat}\n"
)


def env_path() -> Path:
    """The .env file this server reads (same CWD rule as Settings)."""
    return Path.cwd() / _ENV_FILENAME


def _mask(key: str | None) -> str | None:
    """Short, safe preview — never enough to reconstruct the key."""
    if not key:
        return None
    return f"{_MASKED_PREFIX}{key[-4:]}"


def _validated_key(raw: str | None, *, label: str) -> str | None:
    """Normalize one submitted key; None means 'leave unchanged'."""
    if raw is None:
        return None
    cleaned = raw.strip()
    if not cleaned:
        return None
    if not _KEY_PATTERN.match(cleaned):
        raise InvalidInputError(
            f"{label} must be an NVIDIA API key starting with 'nvapi-'."
        )
    return cleaned


def _mode_note(
    *,
    effective_mode: str,
    embedding_key_configured: bool,
    llm_key_configured: bool,
) -> str:
    """Honest operational guidance for the CURRENT effective state."""
    if effective_mode == "demo":
        return (
            "Demo mode is ON — deterministic local retrieval and answers, no "
            "network calls. Live embeddings and keys are untouched; switch to "
            "Live whenever you are ready. Demo mode is never available in "
            "production."
        )
    missing = []
    if not embedding_key_configured:
        missing.append("the embedding key (retrieval returns 503 without it)")
    if not llm_key_configured:
        missing.append("the chat key (answers return 503 without it)")
    if missing:
        return (
            "Live mode is ON but "
            + " and ".join(missing)
            + ". Save the key(s) below — until then those turns return an "
            "honest error instead of an answer."
        )
    return (
        "Live mode is ON — real NVIDIA providers answer now. If the knowledge "
        "base was embedded with an older model, run `python "
        "scripts/index_knowledge.py` once (from backend/) to re-embed it."
    )


def _status() -> ProviderSettingsOut:
    from app.services.provider_mode_service import is_demo_mode

    settings = get_settings()
    demo = is_demo_mode()
    # Effective providers: Demo mode attaches the deterministic local
    # providers; Live mode uses the configured (NVIDIA) providers.
    embedding_provider = "fake" if demo else settings.embedding_provider
    llm_provider = "stub" if demo else settings.llm_provider
    embedding_configured = bool(settings.embedding_api_key)
    llm_configured = bool(settings.nvidia_api_key)
    provider_mode_value = "demo" if demo else "live"
    return ProviderSettingsOut(
        environment=settings.environment,
        provider_mode=provider_mode_value,
        embedding_provider=embedding_provider,
        llm_provider=llm_provider,
        embedding_model=settings.embedding_model,
        llm_model=settings.llm_model,
        embedding_key_configured=embedding_configured,
        llm_key_configured=llm_configured,
        embedding_key_masked=_mask(settings.embedding_api_key),
        llm_key_masked=_mask(settings.nvidia_api_key),
        mode_note=_mode_note(
            effective_mode=provider_mode_value,
            embedding_key_configured=embedding_configured,
            llm_key_configured=llm_configured,
        ),
    )


def get_status() -> ProviderSettingsOut:
    """Current provider state (never key material)."""
    return _status()


def _upsert_env_lines(text: str, updates: dict[str, str]) -> str:
    """Replace the value of the given keys in .env content, in place.

    Comments and every other line are preserved verbatim; keys that are
    absent are appended at the end.
    """
    lines = text.splitlines()
    seen: set[str] = set()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            continue
        name = line.split("=", 1)[0].strip()
        if name in updates:
            lines[index] = f"{name}={updates[name]}"
            seen.add(name)
    for name, value in updates.items():
        if name not in seen:
            lines.append(f"{name}={value}")
    return "\n".join(lines) + "\n"


def save_keys(payload: ProviderKeysUpdate) -> ProviderSettingsOut:
    """Persist submitted keys to .env and refresh the cached settings."""
    embedding_key = _validated_key(payload.embedding_api_key, label="Embedding API key")
    chat_key = _validated_key(payload.nvidia_api_key, label="Chat API key")
    if embedding_key is None and chat_key is None:
        raise InvalidInputError("Provide at least one API key to save.")

    updates: dict[str, str] = {}
    if embedding_key is not None:
        updates["EMBEDDING_API_KEY"] = embedding_key
    if chat_key is not None:
        updates["NVIDIA_API_KEY"] = chat_key

    path = env_path()
    try:
        if path.is_file():
            new_text = _upsert_env_lines(path.read_text(encoding="utf-8"), updates)
        else:
            new_text = _MINIMAL_ENV_TEMPLATE.format(
                embedding=updates.get("EMBEDDING_API_KEY", ""),
                chat=updates.get("NVIDIA_API_KEY", ""),
            )
        path.write_text(new_text, encoding="utf-8")
    except OSError as exc:
        # Never include file content or key values in the error.
        raise InvalidInputError(
            f"Could not write the settings file ({type(exc).__name__})."
        ) from exc

    # Providers are built per request from get_settings(); clearing the
    # cache makes the saved keys take effect on the next request.
    get_settings.cache_clear()

    # Booleans only — key values never reach the log.
    logger.info(
        "provider_keys_updated embedding_saved=%s chat_saved=%s",
        embedding_key is not None,
        chat_key is not None,
    )
    return _status()


def _verify_embedding_key(key: str) -> ProviderVerifyItemOut:
    settings = get_settings()
    try:
        provider = OpenAICompatibleEmbeddingProvider(
            model=settings.embedding_model,
            base_url=settings.embedding_base_url,
            api_key=key,
            dimensions=settings.embedding_dimensions,
            timeout_seconds=min(_VERIFY_TIMEOUT_CAP, settings.embedding_timeout_seconds),
            batch_size=settings.embedding_batch_size,
        )
        provider.embed_text("provider settings verification")
    except Exception as exc:  # noqa: BLE001 - reported honestly, never raised
        return ProviderVerifyItemOut(ok=False, error=str(exc) or type(exc).__name__)
    return ProviderVerifyItemOut(ok=True)


def _verify_chat_key(key: str) -> ProviderVerifyItemOut:
    settings = get_settings()
    try:
        provider = NVIDIAChatProvider(
            model=settings.llm_model,
            base_url=settings.llm_base_url,
            api_key=key,
            timeout_seconds=min(_VERIFY_TIMEOUT_CAP, settings.llm_timeout_seconds),
            temperature=0.0,
            max_tokens=_MIN_VERIFY_TOKENS,
        )
        provider.complete(
            CompletionRequest(
                system_prompt="You are a connectivity test.",
                question="Reply with exactly: OK",
                user_prompt="Reply with exactly: OK",
                task=TASK_GENERATION,
            )
        )
    except Exception as exc:  # noqa: BLE001 - reported honestly, never raised
        return ProviderVerifyItemOut(ok=False, error=str(exc) or type(exc).__name__)
    return ProviderVerifyItemOut(ok=True)


def verify_keys(payload: ProviderVerifyRequest) -> ProviderVerifyOut:
    """One real provider call per submitted key. Nothing is persisted."""
    embedding_key = _validated_key(payload.embedding_api_key, label="Embedding API key")
    chat_key = _validated_key(payload.nvidia_api_key, label="Chat API key")
    if embedding_key is None and chat_key is None:
        raise InvalidInputError("Provide at least one API key to verify.")

    result = ProviderVerifyOut()
    if embedding_key is not None:
        result.embedding = _verify_embedding_key(embedding_key)
    if chat_key is not None:
        result.chat = _verify_chat_key(chat_key)
    return result
