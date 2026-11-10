"""Feedback validation tests."""

from fastapi.testclient import TestClient


def _assistant_message_id(client: TestClient) -> str:
    session = client.post("/api/v1/chat/sessions", json={}).json()
    turn = client.post(
        f"/api/v1/chat/sessions/{session['conversationId']}/messages",
        json={"content": "How do I reset my password?"},
    ).json()
    return turn["assistantMessage"]["id"]


class TestFeedback:
    def test_valid_feedback_created(self, client: TestClient):
        message_id = _assistant_message_id(client)
        response = client.post(
            f"/api/v1/messages/{message_id}/feedback",
            json={"rating": "helpful"},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["rating"] == "helpful"
        assert body["messageId"] == message_id

    def test_negative_feedback_with_reason(self, client: TestClient):
        message_id = _assistant_message_id(client)
        response = client.post(
            f"/api/v1/messages/{message_id}/feedback",
            json={"rating": "not_helpful", "reason": "Not accurate"},
        )
        assert response.status_code == 201
        assert response.json()["reason"] == "Not accurate"

    def test_invalid_rating_rejected(self, client: TestClient):
        message_id = _assistant_message_id(client)
        response = client.post(
            f"/api/v1/messages/{message_id}/feedback",
            json={"rating": "meh"},
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    def test_overlong_reason_rejected(self, client: TestClient):
        message_id = _assistant_message_id(client)
        response = client.post(
            f"/api/v1/messages/{message_id}/feedback",
            json={"rating": "helpful", "reason": "x" * 400},
        )
        assert response.status_code == 422

    def test_unknown_message_404(self, client: TestClient):
        response = client.post(
            "/api/v1/messages/nope/feedback", json={"rating": "helpful"}
        )
        assert response.status_code == 404

    def test_duplicate_feedback_409(self, client: TestClient):
        message_id = _assistant_message_id(client)
        first = client.post(
            f"/api/v1/messages/{message_id}/feedback", json={"rating": "helpful"}
        )
        assert first.status_code == 201
        second = client.post(
            f"/api/v1/messages/{message_id}/feedback", json={"rating": "not_helpful"}
        )
        assert second.status_code == 409
        assert second.json()["error"]["code"] == "CONFLICT"

    def test_feedback_on_customer_message_rejected(self, client: TestClient):
        session = client.post("/api/v1/chat/sessions", json={}).json()
        turn = client.post(
            f"/api/v1/chat/sessions/{session['conversationId']}/messages",
            json={"content": "How do I reset my password?"},
        ).json()
        response = client.post(
            f"/api/v1/messages/{turn['userMessage']['id']}/feedback",
            json={"rating": "helpful"},
        )
        assert response.status_code == 409
