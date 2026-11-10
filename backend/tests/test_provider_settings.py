"""Provider-settings endpoint tests (staff settings dialog).

Covers the honesty guarantees of the new operator surface:
- status responses expose booleans/masks only — never key material;
- key validation (nvapi- prefix, at least one key);
- keys are persisted to the .env file the server reads (temp file in
  tests) with all other lines preserved;
- the settings cache is refreshed so saved keys take effect per request;
- verify maps provider success/failure to honest per-key results without
  persisting anything (network replaced by fakes).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.services import provider_settings_service as svc

GOOD_KEY = "nvapi-" + "a1B2c3D4e5F6g7H8i9J0"  # prefix + 20 token chars


@pytest.fixture()
def env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the service at a temp .env and start from the template."""
    target = tmp_path / ".env"
    target.write_text(
        "# existing settings preserved\n"
        "EMBEDDING_PROVIDER=fake\n"
        "LOG_LEVEL=WARNING\n"
        "EMBEDDING_API_KEY=\n"
        "NVIDIA_API_KEY=\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(svc, "env_path", lambda: target)
    return target


class TestGetStatus:
    def test_status_shape_and_no_key_material(self, client: TestClient):
        response = client.get("/api/v1/admin/provider-settings")
        assert response.status_code == 200
        body = response.json()
        assert body["environment"] == "testing"
        assert body["embeddingProvider"] == "fake"
        assert body["llmProvider"] == "stub"
        assert isinstance(body["embeddingKeyConfigured"], bool)
        assert isinstance(body["llmKeyConfigured"], bool)
        assert "modeNote" in body and body["modeNote"]
        # No key material anywhere in the response.
        assert "nvapi-" not in response.text.replace("nvapi-\u2026", "")

    def test_masked_preview_shows_only_last_four(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ):
        # Simulate a configured key through the environment (highest
        # precedence in Settings), refresh the cache exactly as save_keys
        # does, and assert the honest masked preview.
        monkeypatch.setenv("EMBEDDING_API_KEY", GOOD_KEY)
        from app.core.config import get_settings

        get_settings.cache_clear()
        try:
            body = client.get("/api/v1/admin/provider-settings").json()
            assert body["embeddingKeyConfigured"] is True
            assert body["embeddingKeyMasked"] == "nvapi-\u2026" + GOOD_KEY[-4:]
            assert GOOD_KEY not in body["embeddingKeyMasked"]
        finally:
            get_settings.cache_clear()


class TestSaveKeys:
    def test_requires_at_least_one_key(self, client: TestClient, env_file: Path):
        response = client.put("/api/v1/admin/provider-settings/keys", json={})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    def test_blank_none_and_empty_rejected(self, client: TestClient, env_file: Path):
        for payload in ({"embeddingApiKey": None}, {"embeddingApiKey": "   "}, {}):
            response = client.put("/api/v1/admin/provider-settings/keys", json=payload)
            assert response.status_code == 422, payload
        assert env_file.read_text(encoding="utf-8").startswith("# existing")

    def test_bad_format_rejected_422(self, client: TestClient, env_file: Path):
        for bad in ("sk-1234567890", "nvapi-", "nvapi-short", "hello world"):
            response = client.put(
                "/api/v1/admin/provider-settings/keys",
                json={"embeddingApiKey": bad},
            )
            assert response.status_code == 422, bad
        # The env file was never touched by failed attempts.
        assert "sk-1234567890" not in env_file.read_text(encoding="utf-8")

    def test_valid_key_persisted_and_other_lines_preserved(
        self, client: TestClient, env_file: Path
    ):
        response = client.put(
            "/api/v1/admin/provider-settings/keys",
            json={"embeddingApiKey": GOOD_KEY},
        )
        assert response.status_code == 200
        text = env_file.read_text(encoding="utf-8")
        assert f"EMBEDDING_API_KEY={GOOD_KEY}" in text
        assert "# existing settings preserved" in text  # comments kept
        assert "LOG_LEVEL=WARNING" in text              # other rows kept
        assert "NVIDIA_API_KEY=\n" in text              # untouched row kept
        # The response never echoes the key.
        assert GOOD_KEY not in response.text

    def test_second_save_updates_in_place_and_saves_chat_key(
        self, client: TestClient, env_file: Path
    ):
        client.put(
            "/api/v1/admin/provider-settings/keys",
            json={"embeddingApiKey": GOOD_KEY},
        )
        chat_key = "nvapi-" + "z9y8x7w6v5u4t3s2r1q0p9"
        response = client.put(
            "/api/v1/admin/provider-settings/keys", json={"nvidiaApiKey": chat_key}
        )
        assert response.status_code == 200
        text = env_file.read_text(encoding="utf-8")
        assert text.count("EMBEDDING_API_KEY=") == 1  # updated, not appended
        assert f"NVIDIA_API_KEY={chat_key}" in text

    def test_missing_env_file_is_created(self, client: TestClient, tmp_path: Path):
        target = tmp_path / "fresh.env"
        target.unlink(missing_ok=True)
        original = svc.env_path
        try:
            svc.env_path = lambda: target  # type: ignore[assignment]
            response = client.put(
                "/api/v1/admin/provider-settings/keys",
                json={"embeddingApiKey": GOOD_KEY},
            )
            assert response.status_code == 200
            text = target.read_text(encoding="utf-8")
            assert f"EMBEDDING_API_KEY={GOOD_KEY}" in text
            assert "NVIDIA_API_KEY=" in text
        finally:
            svc.env_path = original  # type: ignore[assignment]


class TestVerifyKeys:
    def test_requires_at_least_one_key(self, client: TestClient):
        response = client.post("/api/v1/admin/provider-settings/verify", json={})
        assert response.status_code == 422

    def test_bad_format_rejected_before_any_network_call(self, client: TestClient):
        response = client.post(
            "/api/v1/admin/provider-settings/verify",
            json={"embeddingApiKey": "not-a-key"},
        )
        assert response.status_code == 422

    def test_verify_success_maps_to_ok(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ):
        class FakeProvider:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            def embed_text(self, text: str) -> list[float]:
                assert "verification" in text
                return [0.0] * 4

        monkeypatch.setattr(svc, "OpenAICompatibleEmbeddingProvider", FakeProvider)
        response = client.post(
            "/api/v1/admin/provider-settings/verify",
            json={"embeddingApiKey": GOOD_KEY},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["embedding"]["ok"] is True
        assert body["embedding"]["error"] is None
        assert body["chat"] is None
        assert GOOD_KEY not in response.text

    def test_verify_failure_maps_to_honest_error(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ):
        class FailingProvider:
            def __init__(self, **kwargs):
                pass

            def embed_text(self, text: str) -> list[float]:
                raise RuntimeError("embedding request failed (HTTPStatusError)")

        monkeypatch.setattr(svc, "OpenAICompatibleEmbeddingProvider", FailingProvider)
        response = client.post(
            "/api/v1/admin/provider-settings/verify",
            json={"embeddingApiKey": GOOD_KEY},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["embedding"]["ok"] is False
        assert "HTTPStatusError" in body["embedding"]["error"]
        assert GOOD_KEY not in response.text

    def test_verify_chat_key_uses_completion(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ):
        captured: dict = {}

        class FakeChat:
            def __init__(self, **kwargs):
                captured.update(kwargs)

            def complete(self, request):
                assert request.system_prompt
                return "OK"

        monkeypatch.setattr(svc, "NVIDIAChatProvider", FakeChat)
        response = client.post(
            "/api/v1/admin/provider-settings/verify",
            json={"nvidiaApiKey": GOOD_KEY},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["chat"]["ok"] is True
        assert body["embedding"] is None
        assert captured["api_key"] == GOOD_KEY


class TestProviderModeToggle:
    """Local Demo/Live switch — explicit, persisted, and reversible."""

    def test_default_is_live(self, client: TestClient):
        body = client.get("/api/v1/admin/provider-settings").json()
        assert body["providerMode"] == "live"
        # Test env configures fake + stub; Live reports those honestly.
        assert body["embeddingProvider"] == "fake"
        assert body["llmProvider"] == "stub"

    def test_switch_to_demo_updates_status_and_health(self, client: TestClient):
        response = client.put(
            "/api/v1/admin/provider-settings/mode", json={"mode": "demo"}
        )
        assert response.status_code == 200
        body = response.json()
        assert body["providerMode"] == "demo"
        assert body["embeddingProvider"] == "fake"
        assert body["llmProvider"] == "stub"
        assert "demo mode is on" in body["modeNote"].lower()

        health = client.get("/health").json()
        assert health["mode"] == "offline_demo"
        assert health["embedding_provider"] == "fake"
        assert health["llm_provider"] == "stub"

    def test_switch_back_to_live(self, client: TestClient):
        client.put("/api/v1/admin/provider-settings/mode", json={"mode": "demo"})
        response = client.put(
            "/api/v1/admin/provider-settings/mode", json={"mode": "live"}
        )
        assert response.status_code == 200
        assert response.json()["providerMode"] == "live"
        assert client.get("/health").json()["mode"] == "offline_demo"

    def test_invalid_mode_rejected(self, client: TestClient):
        response = client.put(
            "/api/v1/admin/provider-settings/mode", json={"mode": "turbo"}
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    def test_demo_mode_refused_in_production(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ):
        from app.core.config import get_settings
        from app.services import provider_mode_service

        monkeypatch.setenv("ENVIRONMENT", "production")
        get_settings.cache_clear()
        try:
            response = client.put(
                "/api/v1/admin/provider-settings/mode", json={"mode": "demo"}
            )
            assert response.status_code == 422
            assert "production" in response.json()["error"]["message"].lower()
            assert provider_mode_service.get_mode() == "live"
        finally:
            get_settings.cache_clear()
