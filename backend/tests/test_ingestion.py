"""End-to-end ingestion tests through the document API.

Every test uses unique content — the startup seed ingests the knowledge
files into the same database, and duplicate content is rejected with 409.
"""

from fastapi.testclient import TestClient


def _post_markdown(client: TestClient, title: str, content: str, source: str | None = None):
    payload = {"title": title, "content": content, "sourceType": "markdown"}
    if source is not None:
        payload["source"] = source
    return client.post("/api/v1/documents", json=payload)


class TestIngestMarkdown:
    def test_valid_markdown_becomes_ready_with_chunks(self, client: TestClient):
        response = _post_markdown(
            client,
            "Export Limits",
            "# Export Limits\n\n## Daily limits\n\nWorkspaces can export "
            "up to 10 reports per day.\n\n## File formats\n\nExports are "
            "available as CSV or JSON.",
        )
        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "READY"
        assert body["sourceType"] == "markdown"
        assert body["chunkCount"] == 2
        assert body["failureReason"] is None
        assert body["processedAt"] is not None
        assert len(body["contentHash"]) == 64

    def test_chunks_carry_full_provenance(self, client: TestClient):
        body = _post_markdown(
            client,
            "Webhook Retries",
            "# Webhook Retries\n\n## Retry policy\n\nFailed deliveries retry "
            "with backoff for up to 24 hours.\n\n## Delivery log\n\nEvery "
            "attempt appears in the delivery log.",
        ).json()
        assert body["status"] == "READY"
        chunks = body["chunks"]
        assert [chunk["chunkIndex"] for chunk in chunks] == [0, 1]
        assert [chunk["sectionId"] for chunk in chunks] == ["retry-policy", "delivery-log"]
        assert chunks[0]["sectionTitle"] == "Retry policy"
        assert all(chunk["pipelineVersion"] == "1" for chunk in chunks)
        assert all(chunk["charCount"] == len(chunk["content"]) for chunk in chunks)

    def test_first_h1_becomes_title(self, client: TestClient):
        body = _post_markdown(
            client,
            "Working Title",
            "# Invoice Exports\n\n## How to export\n\nSelect Invoices then Export.",
        ).json()
        assert body["title"] == "Invoice Exports"


class TestIngestPlainText:
    def test_valid_text_becomes_ready_with_main_section(self, client: TestClient):
        response = client.post(
            "/api/v1/documents",
            json={
                "title": "Maintenance Window Notes",
                "content": (
                    "Northstar Desk runs scheduled maintenance on the first "
                    "Sunday of each month between 02:00 and 04:00 UTC.\n"
                    "During maintenance the dashboard is read-only."
                ),
                "sourceType": "text",
            },
        )
        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "READY"
        assert body["sourceType"] == "text"
        assert len(body["chunks"]) == 1
        assert body["chunks"][0]["sectionId"] == "main"
        assert body["chunks"][0]["sectionTitle"] == "Maintenance Window Notes"


class TestValidation:
    def test_empty_content_rejected_and_no_row_created(self, client: TestClient):
        before = len(client.get("/api/v1/documents").json())
        response = client.post(
            "/api/v1/documents",
            json={"title": "Blank", "content": "   \n\n  ", "sourceType": "markdown"},
        )
        assert response.status_code == 422
        error = response.json()["error"]
        assert error["code"] == "VALIDATION_ERROR"
        after = len(client.get("/api/v1/documents").json())
        assert after == before  # invalid input never creates a document

    def test_unsupported_source_extension_rejected(self, client: TestClient):
        response = client.post(
            "/api/v1/documents",
            json={
                "title": "Spec",
                "content": "# Spec\n\ncontent",
                "source": "specs/spec.docx",
            },
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    def test_unsupported_explicit_source_type_rejected(self, client: TestClient):
        response = client.post(
            "/api/v1/documents",
            json={"title": "Spec", "content": "# Spec\n\ncontent", "sourceType": "html"},
        )
        assert response.status_code == 422

    def test_oversized_content_rejected(self, client: TestClient, monkeypatch):
        from app.core.config import get_settings

        settings = get_settings()
        monkeypatch.setattr(settings, "max_document_bytes", 100)
        response = client.post(
            "/api/v1/documents",
            json={"title": "Huge", "content": "word " * 100, "sourceType": "text"},
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"


class TestDuplicates:
    def test_identical_content_conflicts_with_existing_document_id(self, client: TestClient):
        content = (
            "# Api Keys\n\n## Rotating keys\n\nRotate API keys every 90 days "
            "from Settings → Security."
        )
        first = _post_markdown(client, "API Keys", content).json()
        conflict = _post_markdown(client, "API Keys (renamed)", content)
        assert conflict.status_code == 409
        details = conflict.json()["error"]["details"]
        assert details["documentId"] == first["id"]
        assert details["status"] == "READY"

    def test_seeded_documents_are_not_duplicable(self, client: TestClient):
        """Same title but different content is NOT a duplicate."""
        response = _post_markdown(
            client,
            "Billing & Subscription Plans",
            "# Billing & Subscription Plans\n\n## Different content\n\n"
            "This text differs from the seeded billing document entirely.",
        )
        assert response.status_code == 201


class TestProcessingFailure:
    def test_unreadable_content_is_failed_never_ready(self, client: TestClient):
        response = client.post(
            "/api/v1/documents",
            json={
                "title": "Binary Attachment",
                "content": "ok\x00\x01\x02not really text",
                "sourceType": "markdown",
            },
        )
        assert response.status_code == 422
        error = response.json()["error"]
        assert error["code"] == "PROCESSING_FAILED"
        assert error["details"]["status"] == "FAILED"
        assert "binary" in error["details"]["reason"].lower()

        document_id = error["details"]["documentId"]
        detail = client.get(f"/api/v1/documents/{document_id}").json()
        assert detail["status"] == "FAILED"
        assert detail["failureReason"] is not None
        assert detail["chunkCount"] == 0
        assert detail["chunks"] == []

    def test_failed_document_not_served_as_ready(self, client: TestClient):
        failed = client.post(
            "/api/v1/documents",
            json={"title": "Broken Doc", "content": "\x00\x01", "sourceType": "text"},
        ).json()["error"]["details"]["documentId"]
        documents = client.get("/api/v1/documents").json()
        row = next(d for d in documents if d["id"] == failed)
        assert row["status"] == "FAILED"
        assert row["status"] != "READY"


class TestReadAndReprocess:
    def test_get_document_detail(self, client: TestClient):
        created = _post_markdown(
            client,
            "Session Timeouts",
            "# Session Timeouts\n\n## Default timeout\n\nSessions expire after "
            "12 hours of inactivity.",
        ).json()
        response = client.get(f"/api/v1/documents/{created['id']}")
        assert response.status_code == 200
        detail = response.json()
        assert detail["id"] == created["id"]
        assert detail["content"].startswith("# Session Timeouts")
        assert len(detail["chunks"]) == detail["chunkCount"]

    def test_get_unknown_document_404(self, client: TestClient):
        response = client.get("/api/v1/documents/does-not-exist")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "NOT_FOUND"

    def test_reprocess_is_deterministic(self, client: TestClient):
        created = _post_markdown(
            client,
            "Refund Windows",
            "# Refund Windows\n\n## Standard window\n\nRefunds are available "
            "within 14 days of purchase.\n\n## Exceptions\n\nAnnual contracts "
            "follow the signed agreement.",
        ).json()
        first_chunks = [
            (c["chunkIndex"], c["sectionId"], c["sectionTitle"], c["content"])
            for c in created["chunks"]
        ]

        response = client.post(f"/api/v1/documents/{created['id']}/reprocess")
        assert response.status_code == 200
        again = response.json()
        assert again["status"] == "READY"
        second_chunks = [
            (c["chunkIndex"], c["sectionId"], c["sectionTitle"], c["content"])
            for c in again["chunks"]
        ]
        # Same rules + same content → identical chunking; only row ids differ.
        assert second_chunks == first_chunks
        assert {c["id"] for c in again["chunks"]} != {c["id"] for c in created["chunks"]}
        assert again["contentHash"] == created["contentHash"]

    def test_reprocess_unknown_document_404(self, client: TestClient):
        response = client.post("/api/v1/documents/does-not-exist/reprocess")
        assert response.status_code == 404


class TestSeededKnowledge:
    def test_seed_ingested_all_files_ready(self, client: TestClient):
        documents = client.get("/api/v1/documents").json()
        by_id = {d["id"]: d for d in documents}
        # 7 approved + 1 challenge fixture, all processed by the real pipeline.
        assert {
            "getting-started",
            "account-access",
            "billing",
            "subscriptions",
            "integrations",
            "security",
            "data-retention",
            "legacy-retention-notice",
        } <= set(by_id)
        for document_id in (
            "getting-started",
            "account-access",
            "billing",
            "subscriptions",
            "integrations",
            "security",
            "data-retention",
            "legacy-retention-notice",
        ):
            assert by_id[document_id]["status"] == "READY", document_id
            assert by_id[document_id]["chunkCount"] >= 1
            assert by_id[document_id]["contentHash"] is not None

    def test_conflict_fixture_ingested_and_labeled(self, client: TestClient):
        detail = client.get("/api/v1/documents/legacy-retention-notice").json()
        assert detail["status"] == "READY"
        assert detail["knowledgeStatus"] == "challenge_fixture"
        assert "Challenge fixture" in detail["content"]
        joined = "\n".join(chunk["content"] for chunk in detail["chunks"])
        assert "90 days" in joined  # contradicts data-retention (30 days)

    def test_approved_documents_are_classified_approved(self, client: TestClient):
        documents = client.get("/api/v1/documents").json()
        for document in documents:
            if document["id"] == "legacy-retention-notice":
                continue
            assert document["knowledgeStatus"] == "approved", document["id"]


class TestKnowledgeStatus:
    def test_new_document_defaults_to_approved(self, client: TestClient):
        body = _post_markdown(
            client,
            "Classification Probe",
            "# Classification Probe\n\n## Notes\n\nDefault classification check.",
        ).json()
        assert body["knowledgeStatus"] == "approved"

    def test_client_can_mark_challenge_fixture(self, client: TestClient):
        response = client.post(
            "/api/v1/documents",
            json={
                "title": "Fixture Probe",
                "content": "# Fixture Probe\n\n## Notes\n\nLabeled as a challenge fixture.",
                "sourceType": "markdown",
                "knowledgeStatus": "challenge_fixture",
            },
        )
        assert response.status_code == 201
        assert response.json()["knowledgeStatus"] == "challenge_fixture"

    def test_invalid_classification_rejected(self, client: TestClient):
        response = client.post(
            "/api/v1/documents",
            json={
                "title": "Bad Class",
                "content": "# Bad Class\n\ncontent",
                "sourceType": "markdown",
                "knowledgeStatus": "top_secret",
            },
        )
        assert response.status_code == 422
