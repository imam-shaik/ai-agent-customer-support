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


def _preflight(client: TestClient, path: str, method: str) -> object:
    return client.options(
        path,
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": "content-type",
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
