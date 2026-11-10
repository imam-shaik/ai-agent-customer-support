"""Provider-settings endpoints (staff operator aid, localhost admin surface).

The staff UI submits keys here so the operator does not have to edit
`backend/.env` by hand. Trust model is identical to the other `/admin/*`
routes (unauthenticated localhost admin surface — the documented
production blocker): the dev server binds 127.0.0.1, so only local
operators reach it. Keys are accepted once, stored server-side in
`backend/.env`, never logged, and never returned by any endpoint.
"""

from fastapi import APIRouter

from app.schemas.provider_settings import (
    ProviderKeysUpdate,
    ProviderModeUpdate,
    ProviderSettingsOut,
    ProviderVerifyOut,
    ProviderVerifyRequest,
)
from app.services import provider_mode_service, provider_settings_service

router = APIRouter(tags=["admin"])


@router.get(
    "/admin/provider-settings",
    response_model=ProviderSettingsOut,
    status_code=200,
)
def get_provider_settings() -> ProviderSettingsOut:
    """Provider/status snapshot: booleans + masked previews, never keys."""
    return provider_settings_service.get_status()


@router.put(
    "/admin/provider-settings/mode",
    response_model=ProviderSettingsOut,
    status_code=200,
)
def update_provider_mode(payload: ProviderModeUpdate) -> ProviderSettingsOut:
    """Switch the local workspace between Demo and Live providers.

    Demo uses deterministic local retrieval + generation over the same
    stored knowledge; Live restores the configured NVIDIA providers and
    the existing live index. Persisted server-side; no restart needed.
    """
    provider_mode_service.set_mode(payload.mode)
    return provider_settings_service.get_status()


@router.put(
    "/admin/provider-settings/keys",
    response_model=ProviderSettingsOut,
    status_code=200,
)
def update_provider_keys(payload: ProviderKeysUpdate) -> ProviderSettingsOut:
    """Persist submitted keys to backend/.env and refresh live settings.

    422 — no key submitted, or a key lacks the `nvapi-` prefix. The saved
    state takes effect on the next request.
    """
    return provider_settings_service.save_keys(payload)


@router.post(
    "/admin/provider-settings/verify",
    response_model=ProviderVerifyOut,
    status_code=200,
)
def verify_provider_keys(payload: ProviderVerifyRequest) -> ProviderVerifyOut:
    """One real provider call per submitted key (embed "…", tiny completion).

    The check result is returned per key as ok/error — a wrong key is a
    200 with `ok: false`, not a fabricated success. Nothing is stored.
    """
    return provider_settings_service.verify_keys(payload)
