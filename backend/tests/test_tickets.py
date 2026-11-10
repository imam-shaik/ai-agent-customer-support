"""Escalation ticket tests: creation rules, validation, status events."""

import re

from fastapi.testclient import TestClient


def _escalation_payload(**overrides) -> dict:
    payload = {
        "customerName": "Priya Raman",
        "customerEmail": "priya@harborlight.org",
        "summary": "Nonprofit discount question",
        "originalQuestion": "Do you offer nonprofit discounts?",
        "escalationReason": "No supporting evidence in approved documentation",
    }
    payload.update(overrides)
    return payload


class TestCreateEscalation:
    def test_create_returns_201_with_ticket_shape(
        self, client: TestClient, conversation_with_message: dict
    ):
        response = client.post(
            f"/api/v1/conversations/{conversation_with_message['conversationId']}/escalations",
            json=_escalation_payload(),
        )
        assert response.status_code == 201
        body = response.json()
        assert re.match(r"^NSD-\d{4}-\d{4}$", body["id"])
        assert body["status"] == "OPEN"
        assert body["priority"] == "normal"
        # Conversation context preserved for staff:
        assert len(body["messages"]) >= 2
        assert body["messages"][1]["reply"]["kind"] == "grounded"
        assert body["events"][0]["eventType"] == "ticket_created"

    def test_unknown_conversation_returns_404(self, client: TestClient):
        response = client.post(
            "/api/v1/conversations/missing/escalations", json=_escalation_payload()
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"

    def test_duplicate_escalation_blocked(self, client: TestClient, conversation_with_message: dict):
        url = (
            f"/api/v1/conversations/{conversation_with_message['conversationId']}/escalations"
        )
        first = client.post(url, json=_escalation_payload())
        assert first.status_code == 201

        retry = client.post(url, json=_escalation_payload())
        assert retry.status_code == 409
        error = retry.json()["error"]
        assert error["code"] == "CONFLICT"
        assert error["details"]["ticketId"] == first.json()["id"]

    def test_invalid_email_rejected(self, client: TestClient, conversation_with_message: dict):
        response = client.post(
            f"/api/v1/conversations/{conversation_with_message['conversationId']}/escalations",
            json=_escalation_payload(customerEmail="not-an-email"),
        )
        assert response.status_code == 422

    def test_empty_conversation_rejected(self, client: TestClient):
        session = client.post("/api/v1/chat/sessions", json={}).json()
        response = client.post(
            f"/api/v1/conversations/{session['conversationId']}/escalations",
            json=_escalation_payload(),
        )
        assert response.status_code == 409

    def test_ticket_and_creation_event_commit_atomically(
        self,
        client: TestClient,
        conversation_with_message: dict,
        db_session,
        monkeypatch,
    ):
        from sqlalchemy import func, select

        from app.core.exceptions import AppError
        from app.models import Ticket
        from app.repositories.ticket_repository import TicketRepository

        def fail(*args, **kwargs):
            raise AppError("simulated audit write failure")

        monkeypatch.setattr(TicketRepository, "add_ticket_event_pending", fail)
        response = client.post(
            f"/api/v1/conversations/{conversation_with_message['conversationId']}/escalations",
            json=_escalation_payload(),
        )
        assert response.status_code == 500

        count = db_session.scalar(
            select(func.count())
            .select_from(Ticket)
            .where(
                Ticket.conversation_id
                == conversation_with_message["conversationId"]
            )
        )
        assert count == 0


class TestListAndDetail:
    def test_list_filters_by_status(self, client: TestClient, conversation_with_message: dict):
        client.post(
            f"/api/v1/conversations/{conversation_with_message['conversationId']}/escalations",
            json=_escalation_payload(),
        )
        open_only = client.get("/api/v1/admin/escalations", params={"status": "OPEN"})
        assert open_only.status_code == 200
        body = open_only.json()
        assert body["total"] == len(body["items"]) > 0
        assert all(item["status"] == "OPEN" for item in body["items"])

    def test_invalid_status_filter_rejected(self, client: TestClient):
        response = client.get(
            "/api/v1/admin/escalations", params={"status": "BOGUS"}
        )
        assert response.status_code == 422

    def test_search_matches_customer_name(self, client: TestClient, conversation_with_message: dict):
        client.post(
            f"/api/v1/conversations/{conversation_with_message['conversationId']}/escalations",
            json=_escalation_payload(customerName="Sofia Lindqvist"),
        )
        response = client.get(
            "/api/v1/admin/escalations", params={"q": "sofia"}
        )
        assert response.status_code == 200
        assert response.json()["total"] >= 1

    def test_search_matches_customer_email(
        self, client: TestClient, conversation_with_message: dict
    ):
        email = "email-search-probe@example.org"
        client.post(
            f"/api/v1/conversations/{conversation_with_message['conversationId']}/escalations",
            json=_escalation_payload(customerEmail=email),
        )
        response = client.get(
            "/api/v1/admin/escalations", params={"q": "email-search-probe"}
        )
        assert response.status_code == 200
        assert response.json()["total"] == 1
        assert response.json()["items"][0]["customerEmail"] == email

    def test_status_counts_are_query_scoped(
        self, client: TestClient, conversation_with_message: dict
    ):
        client.post(
            f"/api/v1/conversations/{conversation_with_message['conversationId']}/escalations",
            json=_escalation_payload(customerName="Counts Probe"),
        )
        listed = client.get(
            "/api/v1/admin/escalations", params={"q": "Counts Probe"}
        ).json()
        assert listed["counts"] == {
            "OPEN": 1,
            "IN_PROGRESS": 0,
            "RESOLVED": 0,
        }

        ticket_id = listed["items"][0]["id"]
        changed = client.patch(
            f"/api/v1/admin/escalations/{ticket_id}/status",
            json={"status": "IN_PROGRESS", "expectedStatus": "OPEN"},
        )
        assert changed.status_code == 200

        listed = client.get(
            "/api/v1/admin/escalations", params={"q": "Counts Probe"}
        ).json()
        assert listed["counts"] == {
            "OPEN": 0,
            "IN_PROGRESS": 1,
            "RESOLVED": 0,
        }

    def test_detail_unknown_ticket_404(self, client: TestClient):
        response = client.get("/api/v1/admin/escalations/NSD-2026-0000")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"

    def test_detail_does_not_run_the_agent(
        self, client: TestClient, conversation_with_message: dict, monkeypatch
    ):
        from app.services import agent_service

        response = client.post(
            f"/api/v1/conversations/{conversation_with_message['conversationId']}/escalations",
            json=_escalation_payload(),
        )
        ticket_id = response.json()["id"]

        calls: list[int] = []
        monkeypatch.setattr(
            agent_service,
            "run_agent_turn",
            lambda *args, **kwargs: calls.append(1),
        )

        detail = client.get(f"/api/v1/admin/escalations/{ticket_id}")
        assert detail.status_code == 200
        assert calls == []


class TestStatusChanges:
    def _create(self, client: TestClient, conversation_with_message: dict) -> str:
        response = client.post(
            f"/api/v1/conversations/{conversation_with_message['conversationId']}/escalations",
            json=_escalation_payload(),
        )
        assert response.status_code == 201
        return response.json()["id"]

    def test_status_change_records_event(
        self, client: TestClient, conversation_with_message: dict
    ):
        ticket_id = self._create(client, conversation_with_message)
        response = client.patch(
            f"/api/v1/admin/escalations/{ticket_id}/status",
            json={"status": "IN_PROGRESS", "actor": "maya.chen"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "IN_PROGRESS"
        changed = [
            event for event in body["events"] if event["eventType"] == "status_changed"
        ]
        assert len(changed) == 1
        assert changed[0]["oldValue"] == "OPEN"
        assert changed[0]["newValue"] == "IN_PROGRESS"
        assert changed[0]["actor"] == "maya.chen"

    def test_same_status_is_idempotent(
        self, client: TestClient, conversation_with_message: dict
    ):
        ticket_id = self._create(client, conversation_with_message)
        client.patch(
            f"/api/v1/admin/escalations/{ticket_id}/status", json={"status": "OPEN"}
        )
        detail = client.get(f"/api/v1/admin/escalations/{ticket_id}").json()
        status_events = [
            event for event in detail["events"] if event["eventType"] == "status_changed"
        ]
        assert status_events == []

    def test_invalid_status_rejected(self, client: TestClient, conversation_with_message: dict):
        ticket_id = self._create(client, conversation_with_message)
        response = client.patch(
            f"/api/v1/admin/escalations/{ticket_id}/status",
            json={"status": "CLOSED"},
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    def test_unknown_ticket_status_change_404(self, client: TestClient):
        response = client.patch(
            "/api/v1/admin/escalations/NSD-2026-9999/status",
            json={"status": "RESOLVED"},
        )
        assert response.status_code == 404

    def test_stale_expected_status_is_rejected_without_write(
        self, client: TestClient, conversation_with_message: dict
    ):
        ticket_id = self._create(client, conversation_with_message)
        first = client.patch(
            f"/api/v1/admin/escalations/{ticket_id}/status",
            json={"status": "IN_PROGRESS", "expectedStatus": "OPEN"},
        )
        assert first.status_code == 200

        stale = client.patch(
            f"/api/v1/admin/escalations/{ticket_id}/status",
            json={"status": "RESOLVED", "expectedStatus": "OPEN"},
        )
        assert stale.status_code == 409
        assert stale.json()["error"]["code"] == "CONFLICT"
        assert stale.json()["error"]["details"]["currentStatus"] == "IN_PROGRESS"

        detail = client.get(f"/api/v1/admin/escalations/{ticket_id}").json()
        assert detail["status"] == "IN_PROGRESS"
        changed = [
            event for event in detail["events"] if event["eventType"] == "status_changed"
        ]
        assert len(changed) == 1

    def test_stale_expected_status_to_current_target_is_idempotent(
        self, client: TestClient, conversation_with_message: dict
    ):
        ticket_id = self._create(client, conversation_with_message)
        client.patch(
            f"/api/v1/admin/escalations/{ticket_id}/status",
            json={"status": "IN_PROGRESS", "expectedStatus": "OPEN"},
        )
        duplicate = client.patch(
            f"/api/v1/admin/escalations/{ticket_id}/status",
            json={"status": "IN_PROGRESS", "expectedStatus": "OPEN"},
        )
        assert duplicate.status_code == 200
        changed = [
            event
            for event in duplicate.json()["events"]
            if event["eventType"] == "status_changed"
        ]
        assert len(changed) == 1

    def test_status_and_event_commit_atomically(
        self, client: TestClient, conversation_with_message: dict, monkeypatch
    ):
        from app.core.exceptions import AppError
        from app.repositories.ticket_repository import TicketRepository

        ticket_id = self._create(client, conversation_with_message)

        def fail(*args, **kwargs):
            # AppError is handled by the API's safe 500 envelope, so the
            # test client returns a response instead of re-raising.
            raise AppError("simulated audit write failure")

        monkeypatch.setattr(TicketRepository, "add_ticket_event_pending", fail)
        failed = client.patch(
            f"/api/v1/admin/escalations/{ticket_id}/status",
            json={"status": "IN_PROGRESS", "expectedStatus": "OPEN"},
        )
        assert failed.status_code == 500

        detail = client.get(f"/api/v1/admin/escalations/{ticket_id}").json()
        assert detail["status"] == "OPEN"
        changed = [
            event for event in detail["events"] if event["eventType"] == "status_changed"
        ]
        assert changed == []
