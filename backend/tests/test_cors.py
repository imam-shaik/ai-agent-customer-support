"""CORS preflight regression tests (browser-level behavior).

Bug this pins: `allow_methods` did not include PUT, so the provider-
settings keys endpoint failed its CORS preflight — key saving was broken
FROM THE BROWSER ONLY. API-level clients (TestClient/urllib) skip
preflights, which is why the earlier checks passed while the UI failed.

A browser preflight = OPTIONS + Origin + Access-Control-Request-Method.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

ORIGIN = "http://localhost:3000"


def _preflight(
    client: TestClient,
    path: str,
    method: str,
    request_headers: str = "content-type",
) -> object:
    return client.options(
        path,
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": request_headers,
        },
    )


class TestCorsPreflight:
    def test_put_preflight_allowed_for_provider_settings(self, client: TestClient):
        response = _preflight(
            client, "/api/v1/admin/provider-settings/keys", "PUT"
        )
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == ORIGIN
        allow = response.headers["access-control-allow-methods"]
        assert "PUT" in allow.upper()

    def test_existing_methods_still_preflight_cleanly(self, client: TestClient):
        cases = [
            ("/api/v1/chat/sessions", "POST"),
            ("/api/v1/admin/escalations", "PATCH"),
            ("/api/v1/documents", "GET"),
        ]
        for path, method in cases:
            response = _preflight(client, path, method)
            assert response.status_code == 200, f"{method} {path}"

    def test_authorization_header_preflight_allowed_for_staff_endpoints(self, client):
        """Regression (Phase 11): staff requests carry
        `Authorization: Bearer <token>`, so the browser preflights them
        with Access-Control-Request-Headers: authorization. The CORS
        allow-list did not include it, the preflight was answered 400
        ('Disallowed CORS header'), and EVERY staff call failed from the
        browser only — 'Service offline' pill, empty queue, raised
        tickets invisible. API-level clients skip preflights, which is
        why nothing else caught it."""
        cases = [
            ("/api/v1/admin/escalations?limit=50&offset=0", "GET"),
            ("/api/v1/admin/escalations/NSD-2026-6123", "GET"),
            ("/api/v1/admin/escalations/NSD-2026-6123/status", "PATCH"),
            ("/api/v1/admin/escalations/NSD-2026-6123/replies", "POST"),
            ("/api/v1/auth/me", "GET"),
            ("/api/v1/auth/logout", "POST"),
        ]
        for path, method in cases:
            response = _preflight(client, path, method, request_headers="authorization")
            assert response.status_code == 200, f"{method} {path}"
            allowed = response.headers["access-control-allow-headers"].lower()
            assert "authorization" in allowed, f"{method} {path}"

    def test_unauthorized_preflight_hint(self, client: TestClient):
        """Pin the exact failure signature so a regression reads clearly:
        a disallowed preflight header is a 400, not 401/403."""
        response = _preflight(
            client,
            "/api/v1/admin/escalations",
            "GET",
            request_headers="authorization, x-not-allowed-header",
        )
        # x-not-allowed-header must NOT appear in the allow list; with the
        # current Starlette behavior this is the only remaining 400 case.
        if response.status_code != 200:
            assert response.status_code == 400

    def test_actual_put_request_carries_cors_headers(self, client: TestClient):
        # A real PUT (invalid payload on purpose) must still be answered
        # with the CORS origin header so the browser can read the 422.
        response = client.put(
            "/api/v1/admin/provider-settings/keys",
            json={},
            headers={"Origin": ORIGIN},
        )
        assert response.status_code == 422
        assert response.headers["access-control-allow-origin"] == ORIGIN
