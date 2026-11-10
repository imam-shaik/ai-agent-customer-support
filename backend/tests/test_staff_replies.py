"""Staff reply composer: send a message to the ticket's customer email.

Covers the honest dispatch contract: without SMTP configured the reply
is stored with `emailDispatched=false` and a safe note (never a fake
"sent"), the audit event lands in one commit with the reply, and the
detail endpoint renders the stored reply history.
"""

import uuid

import pytest

from app.api.deps import get_current_staff
from app.main import app


@pytest.fixture()
def real_auth():
    """Remove the suite-wide auth bypass for this test only."""
    app.dependency_overrides.pop(get_current_staff, None)
    yield


def _escalate(client, conversation_id: str) -> dict:
    response = client.post(
        f"/api/v1/conversations/{conversation_id}/escalations",
        json={
            "customerName": "Sofia Marques",
            "customerEmail": f"sofia-{uuid.uuid4().hex[:8]}@example.com",
            "summary": "Composer probe",
            "originalQuestion": "How do I invite my team?",
            "escalationReason": "Staff reply composer test",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_reply_stored_with_honest_dispatch_state(client, conversation_with_message):
    ticket = _escalate(client, conversation_with_message["conversationId"])

    response = client.post(
        f"/api/v1/admin/escalations/{ticket['id']}/replies",
        json={"message": "We checked your workspace — invites are under Settings → Team."},
    )
    assert response.status_code == 201, response.text
    reply = response.json()
    assert reply["staffName"] == "Test Staff"  # the suite's bypass identity
    assert reply["sentTo"] == ticket["customerEmail"]
    # SMTP deliberately unconfigured in the suite → NOT delivered, with
    # an honest note. Never a fake "sent".
    assert reply["emailDispatched"] is False
    assert "NOT delivered" in reply["dispatchNote"]


def test_reply_appears_in_detail_and_records_event(client, conversation_with_message):
    ticket = _escalate(client, conversation_with_message["conversationId"])
    message = "Invites live under Settings → Team."

    client.post(f"/api/v1/admin/escalations/{ticket['id']}/replies", json={"message": message})

    detail = client.get(f"/api/v1/admin/escalations/{ticket['id']}").json()
    assert len(detail["replies"]) == 1
    assert detail["replies"][0]["body"] == message
    assert detail["replies"][0]["sentTo"] == ticket["customerEmail"]

    event_types = [event["eventType"] for event in detail["events"]]
    assert "staff_reply" in event_types
    event = next(e for e in detail["events"] if e["eventType"] == "staff_reply")
    assert event["newValue"] == "stored"  # honest: no email went out here
    assert event["actor"] == "Test Staff"


def test_multiple_replies_are_ordered_chronologically(client, conversation_with_message):
    ticket = _escalate(client, conversation_with_message["conversationId"])

    for index in range(3):
        response = client.post(
            f"/api/v1/admin/escalations/{ticket['id']}/replies",
            json={"message": f"Update {index + 1} of 3."},
        )
        assert response.status_code == 201

    detail = client.get(f"/api/v1/admin/escalations/{ticket['id']}").json()
    bodies = [reply["body"] for reply in detail["replies"]]
    assert bodies == ["Update 1 of 3.", "Update 2 of 3.", "Update 3 of 3."]


def test_reply_unknown_ticket_404(client):
    response = client.post(
        "/api/v1/admin/escalations/NSD-2026-0000/replies", json={"message": "hello"}
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_reply_empty_message_422(client, conversation_with_message):
    ticket = _escalate(client, conversation_with_message["conversationId"])
    response = client.post(
        f"/api/v1/admin/escalations/{ticket['id']}/replies", json={"message": "   "}
    )
    assert response.status_code == 422


def test_reply_requires_sign_in(client, real_auth, conversation_with_message):
    ticket = _escalate(client, conversation_with_message["conversationId"])
    denied = client.post(
        f"/api/v1/admin/escalations/{ticket['id']}/replies",
        json={"message": "should not work without a session"},
    )
    assert denied.status_code == 401
    assert denied.json()["error"]["code"] == "UNAUTHORIZED"


def test_reply_with_smtp_configured_reports_dispatched(
    client, conversation_with_message, monkeypatch
):
    """Configured SMTP → dispatched=True. smtplib is replaced with a fake
    server so no real network call ever happens."""
    import app.services.email_service as email_service

    sent: list[dict] = []

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            self.host = host

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def ehlo(self):
            return None

        def starttls(self, context=None):
            return None

        def login(self, username, password):
            return None

        def send_message(self, message):
            sent.append({"to": message["To"], "subject": message["Subject"]})

    class FakeSettings:
        smtp_host = "smtp.example.com"
        smtp_port = 587
        smtp_username = "support@example.com"
        smtp_password = "secret"
        smtp_from = "support@example.com"
        smtp_timeout_seconds = 5.0

    monkeypatch.setattr(email_service, "get_settings", lambda: FakeSettings())
    monkeypatch.setattr(email_service.smtplib, "SMTP", FakeSMTP)

    ticket = _escalate(client, conversation_with_message["conversationId"])
    response = client.post(
        f"/api/v1/admin/escalations/{ticket['id']}/replies",
        json={"message": "This one goes out over (fake) SMTP."},
    )
    assert response.status_code == 201, response.text
    reply = response.json()
    assert reply["emailDispatched"] is True
    assert reply["dispatchNote"] is None
    assert reply["dispatchChannel"] == "smtp"
    assert len(sent) == 1
    assert sent[0]["to"] == ticket["customerEmail"]
    assert ticket["id"] in sent[0]["subject"]

    # The audit event records the honest outcome.
    detail = client.get(f"/api/v1/admin/escalations/{ticket['id']}").json()
    event = next(e for e in detail["events"] if e["eventType"] == "staff_reply")
    assert event["newValue"] == "emailed"


def test_reply_via_gmail_channel_is_a_honest_handoff(
    client, conversation_with_message, monkeypatch
):
    """channel="gmail": NO server dispatch is attempted (SMTP not touched
    even if configured). The reply is stored as a Gmail hand-off —
    emailDispatched stays False (this app cannot see Gmail's outbox),
    with the gmail channel recorded for the UI badge."""
    import app.services.email_service as email_service

    def _fail_dispatch(**kwargs):
        raise AssertionError("gmail channel must not attempt SMTP dispatch")

    monkeypatch.setattr(email_service, "dispatch_email", _fail_dispatch)

    ticket = _escalate(client, conversation_with_message["conversationId"])
    response = client.post(
        f"/api/v1/admin/escalations/{ticket['id']}/replies",
        json={
            "message": "Invites are under Settings → Team.",
            "channel": "gmail",
        },
    )
    assert response.status_code == 201, response.text
    reply = response.json()
    assert reply["dispatchChannel"] == "gmail"
    assert reply["emailDispatched"] is False
    assert "Gmail" in (reply["dispatchNote"] or "")

    detail = client.get(f"/api/v1/admin/escalations/{ticket['id']}").json()
    assert detail["replies"][0]["dispatchChannel"] == "gmail"
    event = next(e for e in detail["events"] if e["eventType"] == "staff_reply")
    assert event["newValue"] == "gmail"
