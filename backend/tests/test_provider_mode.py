"""Demo-mode end-to-end tests.

Demo is an explicit local mode: deterministic lexical retrieval over the
stored knowledge chunks + the stub generator. These tests prove it
answers with real citations, never needs live vectors, and never mutates
the live index.
"""

from __future__ import annotations

from sqlalchemy import select

from app.models.entities import DocumentChunk


def _enable_demo(client) -> None:
    response = client.put(
        "/api/v1/admin/provider-settings/mode", json={"mode": "demo"}
    )
    assert response.status_code == 200


def _ask(client, question: str) -> dict:
    session = client.post("/api/v1/chat/sessions", json={}).json()
    response = client.post(
        f"/api/v1/chat/sessions/{session['conversationId']}/messages",
        json={"content": question},
    )
    assert response.status_code == 200, response.text
    return response.json()


class TestDemoMode:
    def test_demo_answers_with_citation(self, client):
        _enable_demo(client)
        turn = _ask(client, "How do I reset my password?")
        reply = turn["assistantMessage"]["reply"]
        assert reply["kind"] == "grounded"
        assert reply["citations"], "demo answers must carry real citations"
        assert reply["citations"][0]["docId"] == "account-access"
        assert reply["citations"][0]["snippet"]

    def test_demo_dead_end_offers_escalation(self, client):
        _enable_demo(client)
        turn = _ask(client, "What is the airspeed velocity of an unladen swallow?")
        reply = turn["assistantMessage"]["reply"]
        assert reply["kind"] in {"unsupported", "uncertain"}
        assert reply.get("escalationOffer")

    def test_demo_works_without_live_embeddings(self, client, db_session):
        """Demo retrieval reads chunk content, not the live vector column."""
        _enable_demo(client)
        chunks = db_session.scalars(select(DocumentChunk)).all()
        saved = [
            (chunk, chunk.embedding, chunk.embedding_model, chunk.embedding_fingerprint)
            for chunk in chunks
        ]
        try:
            # Hide every live vector: live retrieval would now return nothing.
            for chunk in chunks:
                chunk.embedding = None
                chunk.embedding_model = None
                chunk.embedding_fingerprint = None
            db_session.commit()

            turn = _ask(client, "How do I reset my password?")
            reply = turn["assistantMessage"]["reply"]
            assert reply["kind"] == "grounded"
            assert reply["citations"]
        finally:
            # Restore the session index for the tests that follow.
            for chunk, embedding, model, fingerprint in saved:
                chunk.embedding = embedding
                chunk.embedding_model = model
                chunk.embedding_fingerprint = fingerprint
            db_session.commit()

    def test_demo_answers_misspelled_question(self, client):
        """8b-7: demo mode corrects spelling against the corpus vocabulary
        — the deterministic analog of the live pipeline's typo tolerance
        (assessment search_query + typo-robust embeddings). Observed
        2026-11-12: "when am i billled?" dead-ended in weak_relevance
        while the correctly-spelled question grounded."""
        _enable_demo(client)
        turn = _ask(client, "when am i billled?")
        reply = turn["assistantMessage"]["reply"]
        assert reply["kind"] == "grounded"
        assert reply["citations"], "the corrected question must ground with citations"

    def test_demo_filler_greeting_gets_typed_greeting(self, client):
        """8b-7: "ok hi" is small talk in demo mode too — the typed
        greeting steers back to a valid support question instead of the
        dead-end uncertain reply (observed in live mode 2026-11-12)."""
        _enable_demo(client)
        turn = _ask(client, "ok hi")
        reply = turn["assistantMessage"]["reply"]
        assert reply["kind"] == "greeting"
        assert reply["options"], "the greeting offers valid-question suggestions"
        assert turn["assistantMessage"]["citations"] == []
        assert "escalationOffer" not in reply

    def test_demo_turn_does_not_rewrite_live_embeddings(self, client, db_session):
        _enable_demo(client)
        before = [
            (chunk.id, chunk.embedding_model, chunk.embedding_fingerprint)
            for chunk in db_session.scalars(
                select(DocumentChunk).order_by(DocumentChunk.id)
            ).all()
        ]

        _ask(client, "How do I reset my password?")

        db_session.expire_all()
        after = [
            (chunk.id, chunk.embedding_model, chunk.embedding_fingerprint)
            for chunk in db_session.scalars(
                select(DocumentChunk).order_by(DocumentChunk.id)
            ).all()
        ]
        assert before == after
