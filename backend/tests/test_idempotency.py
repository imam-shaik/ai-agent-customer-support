"""Phase 9: turn idempotency, history, feedback hydration.

Covers the review-mandated cases:
- completed turn replay (no duplicate turn, no agent call);
- retry after a failed turn reuses the customer message;
- same request id with different content is rejected;
- concurrent duplicate assistant persistence is blocked by the database;
- history restoration with citations, feedback, and active ticket.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError


def _session(client: TestClient) -> str:
    response = client.post("/api/v1/chat/sessions", json={})
    assert response.status_code == 201
    return response.json()["conversationId"]


def _post(
    client: TestClient, conversation_id: str, content: str, request_id: str | None = None
):
    payload: dict = {"content": content}
    if request_id is not None:
        payload["clientRequestId"] = request_id
    return client.post(
        f"/api/v1/chat/sessions/{conversation_id}/messages", json=payload
    )


def _turn(client: TestClient, conversation_id: str, content: str, request_id: str) -> dict:
    response = _post(client, conversation_id, content, request_id)
    assert response.status_code == 200, response.text
    return response.json()


class TestTurnIdempotency:
    def test_completed_turn_is_replayed_without_reprocessing(
        self, client: TestClient, monkeypatch
    ):
        from app.services import agent_service

        calls: list[int] = []
        original = agent_service.run_agent_turn

        def spy(*args, **kwargs):
            calls.append(1)
            return original(*args, **kwargs)

        monkeypatch.setattr(agent_service, "run_agent_turn", spy)

        conversation_id = _session(client)
        request_id = str(uuid.uuid4())
        first = _turn(client, conversation_id, "How do I reset my password?", request_id)
        second = _turn(client, conversation_id, "How do I reset my password?", request_id)

        assert calls == [1], "a completed replay must not call the agent again"
        assert second["userMessage"]["id"] == first["userMessage"]["id"]
        assert second["assistantMessage"]["id"] == first["assistantMessage"]["id"]
        assert second["assistantMessage"]["reply"] == first["assistantMessage"]["reply"]
        assert len(second["assistantMessage"]["citations"]) == len(
            first["assistantMessage"]["citations"]
        )
        assert second["userMessage"]["clientRequestId"] == request_id

    def test_retry_after_failure_reuses_the_customer_message(
        self, client: TestClient, monkeypatch, db_session
    ):
        from app.core.exceptions import GenerationFailedError
        from app.models import Message
        from app.services import agent_service

        original = agent_service.run_agent_turn
        state = {"fail": True}

        def flaky(*args, **kwargs):
            if state["fail"]:
                state["fail"] = False
                raise GenerationFailedError("simulated provider failure")
            return original(*args, **kwargs)

        monkeypatch.setattr(agent_service, "run_agent_turn", flaky)

        conversation_id = _session(client)
        request_id = str(uuid.uuid4())

        failed = _post(client, conversation_id, "When am I billed?", request_id)
        assert failed.status_code == 502
        assert failed.json()["error"]["code"] == "GENERATION_FAILED"

        rows = list(
            db_session.scalars(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at)
            ).all()
        )
        assert [row.role for row in rows] == ["user"]
        assert rows[0].client_request_id == request_id

        retried = _turn(client, conversation_id, "When am I billed?", request_id)
        assert retried["userMessage"]["id"] == rows[0].id
        assert retried["assistantMessage"]["reply"]["kind"] == "grounded"

        rows = list(
            db_session.scalars(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at)
            ).all()
        )
        assert [row.role for row in rows] == ["user", "assistant"]

    def test_same_request_id_with_different_content_is_rejected(
        self, client: TestClient, db_session
    ):
        from app.models import Message

        conversation_id = _session(client)
        request_id = str(uuid.uuid4())
        _turn(client, conversation_id, "How do I reset my password?", request_id)

        response = _post(client, conversation_id, "When am I billed?", request_id)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "CONFLICT"
        assert response.json()["error"]["details"]["clientRequestId"] == request_id

        rows = list(
            db_session.scalars(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at)
            ).all()
        )
        assert [row.role for row in rows] == ["user", "assistant"]

    def test_malformed_request_id_is_rejected_before_writing(
        self, client: TestClient, db_session
    ):
        from app.models import Message

        conversation_id = _session(client)
        response = _post(client, conversation_id, "hello", "not-a-uuid")
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

        count = db_session.scalar(
            select(func.count())
            .select_from(Message)
            .where(Message.conversation_id == conversation_id)
        )
        assert count == 0

    def test_database_blocks_a_second_assistant_reply_for_one_turn(
        self, client: TestClient, db_session
    ):
        from app.models import Message
        from app.repositories.conversation_repository import ConversationRepository

        repo = ConversationRepository(db_session)
        conversation = repo.create_conversation()
        user = repo.add_message(conversation.id, role="user", content="Hello?")

        repo.add_assistant_turn(
            conversation.id,
            content="First reply",
            reply={"kind": "unsupported", "text": "First reply"},
            reply_to_message_id=user.id,
            citations=[],
        )

        with pytest.raises(IntegrityError):
            repo.add_assistant_turn(
                conversation.id,
                content="Second reply",
                reply={"kind": "unsupported", "text": "Second reply"},
                reply_to_message_id=user.id,
                citations=[],
            )
        db_session.rollback()

        assistants = db_session.scalar(
            select(func.count())
            .select_from(Message)
            .where(
                Message.conversation_id == conversation.id,
                Message.role == "assistant",
            )
        )
        assert assistants == 1

    def test_legacy_without_request_id_still_works(self, client: TestClient):
        conversation_id = _session(client)
        first = _post(client, conversation_id, "How do I reset my password?")
        assert first.status_code == 200
        second = _post(client, conversation_id, "When am I billed?")
        assert second.status_code == 200
        assert first.json()["userMessage"]["clientRequestId"] is None


class TestConversationHistory:
    def test_history_returns_messages_citations_and_no_ticket(
        self, client: TestClient
    ):
        conversation_id = _session(client)
        turn = _turn(client, conversation_id, "How do I reset my password?", str(uuid.uuid4()))

        response = client.get(f"/api/v1/chat/sessions/{conversation_id}/messages")
        assert response.status_code == 200
        body = response.json()
        assert body["conversationId"] == conversation_id
        assert [m["role"] for m in body["messages"]] == ["user", "assistant"]
        assert body["messages"][0]["id"] == turn["userMessage"]["id"]
        assert body["messages"][1]["id"] == turn["assistantMessage"]["id"]
        assert body["messages"][1]["reply"]["kind"] == "grounded"
        assert body["messages"][1]["citations"]
        assert body["messages"][1]["feedback"] is None
        assert body["activeTicket"] is None

    def test_unknown_conversation_history_is_404(self, client: TestClient):
        response = client.get("/api/v1/chat/sessions/does-not-exist/messages")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"

    def test_feedback_is_restored_by_history(self, client: TestClient):
        conversation_id = _session(client)
        turn = _turn(client, conversation_id, "How do I reset my password?", str(uuid.uuid4()))
        assistant_id = turn["assistantMessage"]["id"]

        feedback = client.post(
            f"/api/v1/messages/{assistant_id}/feedback",
            json={"rating": "helpful"},
        )
        assert feedback.status_code == 201

        history = client.get(
            f"/api/v1/chat/sessions/{conversation_id}/messages"
        ).json()
        restored = next(m for m in history["messages"] if m["id"] == assistant_id)
        assert restored["feedback"]["rating"] == "helpful"
        assert restored["feedback"]["messageId"] == assistant_id

        duplicate = client.post(
            f"/api/v1/messages/{assistant_id}/feedback",
            json={"rating": "helpful"},
        )
        assert duplicate.status_code == 409

    def test_active_ticket_is_restored_by_history(self, client: TestClient):
        conversation_id = _session(client)
        _turn(client, conversation_id, "How do I reset my password?", str(uuid.uuid4()))

        escalation = client.post(
            f"/api/v1/conversations/{conversation_id}/escalations",
            json={
                "customerName": "Alex Rivera",
                "customerEmail": "alex@company.com",
                "summary": "Password reset did not arrive",
                "originalQuestion": "How do I reset my password?",
            },
        )
        assert escalation.status_code == 201, escalation.text
        ticket = escalation.json()

        history = client.get(
            f"/api/v1/chat/sessions/{conversation_id}/messages"
        ).json()
        assert history["activeTicket"]["id"] == ticket["id"]
        assert history["activeTicket"]["status"] == "OPEN"
        assert history["activeTicket"]["customerEmail"] == "alex@company.com"
        assert history["activeTicket"]["messageCount"] == 2

    def test_replay_includes_recorded_feedback(self, client: TestClient):
        conversation_id = _session(client)
        request_id = str(uuid.uuid4())
        turn = _turn(client, conversation_id, "How do I reset my password?", request_id)
        assistant_id = turn["assistantMessage"]["id"]

        client.post(
            f"/api/v1/messages/{assistant_id}/feedback",
            json={"rating": "not_helpful", "reason": "Hard to follow"},
        )
        replay = _turn(client, conversation_id, "How do I reset my password?", request_id)
        assert replay["assistantMessage"]["id"] == assistant_id
        assert replay["assistantMessage"]["feedback"]["rating"] == "not_helpful"
