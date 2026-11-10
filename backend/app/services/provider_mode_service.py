"""Runtime Demo/Live provider mode (local operator surface).

The configured providers remain the LIVE providers. Demo mode is an
explicit, local-only override that answers with deterministic local
providers so the application can be reviewed without API keys:

    live  — configured NVIDIA embeddings + chat model (honest 503s when
            a key is missing; the live pgvector index is used).
    demo  — local lexical retrieval over the SAME stored knowledge
            chunks + the deterministic stub generator. No network, no
            keys, and no writes to the live embedding columns.

Safety rules:
- Demo mode is refused in production (a deployment must never serve
  deterministic demo answers to real traffic).
- The toggle is persisted server-side in ``backend/data/provider-mode.json``
  and read on every request, so no restart is needed.
- Switching modes never rewrites embeddings or provider keys. Returning
  to Live reuses whatever live index was already built.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from app.core.config import get_settings
from app.core.exceptions import InvalidInputError
from app.core.logging import get_logger

logger = get_logger("app.provider_mode")

MODE_LIVE = "live"
MODE_DEMO = "demo"
VALID_MODES = (MODE_LIVE, MODE_DEMO)

_DEFAULT_FILENAME = "provider-mode.json"


def mode_path() -> Path:
    """Persisted mode file (overridable so tests stay hermetic)."""
    override = os.environ.get("PROVIDER_MODE_FILE")
    if override:
        return Path(override)
    return Path.cwd() / "data" / _DEFAULT_FILENAME


def get_mode() -> str:
    """Effective mode. Production always reports ``live``."""
    if get_settings().environment == "production":
        return MODE_LIVE
    path = mode_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        mode = str(payload.get("mode", MODE_LIVE)).strip().lower()
    except (OSError, ValueError, TypeError):
        # Missing/corrupt file: the safe default is the configured live
        # providers, never a silent demo override.
        return MODE_LIVE
    return mode if mode in VALID_MODES else MODE_LIVE


def is_demo_mode() -> bool:
    return get_mode() == MODE_DEMO


def set_mode(mode: str) -> str:
    """Persist a mode. Refuses demo outside local/dev environments."""
    normalized = (mode or "").strip().lower()
    if normalized not in VALID_MODES:
        raise InvalidInputError("mode must be 'demo' or 'live'.")
    if normalized == MODE_DEMO and get_settings().environment == "production":
        raise InvalidInputError("Demo mode is not available in production.")

    path = mode_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Direct write is intentional: a temp-file replace can fail on
        # Windows while another process holds the target open.
        path.write_text(
            json.dumps({"mode": normalized}, indent=2) + "\n", encoding="utf-8"
        )
    except OSError as exc:
        raise InvalidInputError(
            f"Could not save the provider mode ({type(exc).__name__})."
        ) from exc

    logger.info("provider_mode_changed mode=%s", normalized)
    return normalized
