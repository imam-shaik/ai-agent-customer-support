"""Tests: optional phone + conversation ticket list (my tickets)."""
from __future__ import annotations

import json
import re

from fastapi.testclient import TestClient


def _escalation_payload(**overrides) -> dict:
    payload = {
        "customerName": "Phone Tester",
        "customerEmail": "phone@example.com",
        "summary": "Phone field verification",
        "originalQuestion": "How do I reset my password?",
        "escalationReason": "Verifying the optional phone field",
    }
    payload.update(overrides)
    return payload


class TestOptionalPhone:
    def test_ticket_created_without_phone_stores_null(
        self, client: TestClient, conversation_with_message: dict
    ):
        response = client.post(
            f"/api/v1/conversations/{conversation_with_message['conversationId']}/escalations",
            json=_escalation_payload(),
        )
        assert response.status_code == 201
        assert response.json()["customerPhone"] is None

    def test_ticket_created_with_phone_stores_it(
        self, client: TestClient, conversation_with_message: dict
    ):
        response = client.post(
            f"/api/v1/conversations/{conversation_with_message['conversationId']}/escalations",
            json=_escalation_payload(customerPhone="+91 98765-43210"),
        )
        assert response.status_code == 201
        body = response.json()
        assert body["customerPhone"] == "+91 98765-43210"
        # Staff detail exposes the same value.
        detail = client.get(f"/api/v1/admin/escalations/{body['id']}").json()
        assert detail["customerPhone"] == "+91 98765-43210"

    def test_invalid_phone_rejected_422(
        self, client: TestClient, conversation_with_message: dict
    ):
        for bad in ("call me", "abc12345678901234567890", "12"):
            response = client.post(
                f"/api/v1/conversations/{conversation_with_message['conversationId']}/escalations",
                json=_escalation_payload(customerPhone=bad),
            )
            assert response.status_code == 422, bad
            assert "customerPhone" in json.dumps(response.json()["error"]["details"])

    def test_whitespace_phone_is_trimmed(
        self, client: TestClient, conversation_with_message: dict
    ):
        response = client.post(
            f"/api/v1/conversations/{conversation_with_message['conversationId']}/escalations",
            json=_escalation_payload(customerPhone="  +1 (555) 010-2030  "),
        )
        assert response.status_code == 201
        assert response.json()["customerPhone"] == "+1 (555) 010-2030"


class TestConversationTicketList:
    def test_lists_all_tickets_newest_first_with_time(
        self, client: TestClient, conversation_with_message: dict
    ):
        cid = conversation_with_message["conversationId"]
        first = client.post(
            f"/api/v1/conversations/{cid}/escalations", json=_escalation_payload()
        )
        assert first.status_code == 201
        first_id = first.json()["id"]

        # Resolve the first ticket so a second can be raised (contract:
        # one UNRESOLVED ticket per conversation).
        client.patch(
            f"/api/v1/admin/escalations/{first_id}/status",
            json={"status": "RESOLVED", "actor": "Test"},
        )
        second = client.post(
            f"/api/v1/conversations/{cid}/escalations",
            json=_escalation_payload(summary="Second issue after resolution"),
        )
        assert second.status_code == 201
        second_id = second.json()["id"]

        listing = client.get(f"/api/v1/conversations/{cid}/escalations")
        assert listing.status_code == 200
        body = listing.json()
        assert body["conversationId"] == cid
        assert body["total"] == 2
        assert [item["id"] for item in body["items"]] == [second_id, first_id]
        # Timestamps present for every row (the 'with the time' requirement).
        for item in body["items"]:
            assert re.match(r"^\d{4}-\d{2}-\d{2}T", item["createdAt"])
            assert item["status"] in ("OPEN", "IN_PROGRESS", "RESOLVED")
            assert item["summary"]

    def test_unknown_conversation_404(self, client: TestClient):
        response = client.get("/api/v1/conversations/does-not-exist/escalations")
        assert response.status_code == 404

    def test_empty_conversation_lists_zero(self, client: TestClient):
        session = client.post("/api/v1/chat/sessions", json={}).json()
        listing = client.get(
            f"/api/v1/conversations/{session['conversationId']}/escalations"
        )
        assert listing.status_code == 200
        body = listing.json()
        assert body["total"] == 0
        assert body["items"] == []
