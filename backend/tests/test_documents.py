"""Document API contract tests (Phase 6): honest status, client limits.

Deep ingestion behavior lives in test_ingestion.py; this file pins the
contract details clients rely on.
"""

from fastapi.testclient import TestClient


class TestDocuments:
    def test_list_returns_seeded_approved_documents(self, client: TestClient):
        response = client.get("/api/v1/documents")
        assert response.status_code == 200
        body = response.json()
        assert len(body) >= 6
        ids = {document["id"] for document in body}
        assert {"account-access", "billing", "security"} <= ids

    def test_created_document_is_processed_not_pending(
        self, client: TestClient, db_session
    ):
        """Synchronous ingestion: 201 means the pipeline already ran."""
        from app.models import Document

        response = client.post(
            "/api/v1/documents",
            json={
                "title": "Ticket Tags",
                "content": "# Ticket Tags\n\n## Tagging rules\n\nTags are applied "
                "manually by staff from the ticket sidebar.",
                "sourceType": "markdown",
            },
        )
        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "READY"
        assert body["chunkCount"] >= 1
        # Canary cleanup (FK CASCADE removes chunks + embeddings): a leftover
        # document would surface as a pending chunk in test_indexing, since
        # the corpus is indexed session-wide in Phase 8A (autouse fixture).
        document = db_session.get(Document, body["id"])
        assert document is not None
        db_session.delete(document)
        db_session.commit()

    def test_client_cannot_set_status_field(self, client: TestClient):
        response = client.post(
            "/api/v1/documents",
            json={"title": "Something", "status": "READY"},
        )
        assert response.status_code == 422  # extra="forbid"

    def test_empty_title_rejected(self, client: TestClient):
        response = client.post("/api/v1/documents", json={"title": "   "})
        assert response.status_code == 422

    def test_extra_field_rejected(self, client: TestClient):
        response = client.post(
            "/api/v1/documents",
            json={"title": "Something", "unexpected": True},
        )
        assert response.status_code == 422
