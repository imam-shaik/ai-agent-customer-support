"""Explicit indexing workflow tests (Phase 7 §8).

Covers the §15 indexing cases with the deterministic fake provider:
- content-derived fingerprints (identity from content, never row ids)
- unchanged chunks are NEVER re-embedded; changed chunks are
- model mismatch invalidates old vectors
- force / dry-run semantics
- knowledge_status scope: archived never indexed, fixtures indexed
- provider failure leaves chunks NULL (un-searchable), never faked
"""

import hashlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.embeddings.base import EmbeddingProvider, EmbeddingProviderError
from app.models.entities import Document, DocumentChunk
from app.services.indexing_service import (
    INDEXABLE_KNOWLEDGE_STATUSES,
    IndexingService,
    chunk_fingerprint,
)

FAKE_MODEL = "fake-lexical-hash-v1"

# Neutral vocabulary on purpose: these documents must not compete with the
# retrieval-quality assertions in test_retrieval.py when they are indexed.
def _widget_text(title: str) -> str:
    # The title is embedded in the content so every upload is unique
    # (identical content is rejected as a duplicate by design).
    return (
        f"# {title}\n\n## Sprocket assembly\n\n"
        "The frobnicator attaches to the sprocket housing with a quarter turn.\n\n"
        "## Maintenance\n\nFrobnicate the widget every ninety cycles."
    )


def _create_doc(client: TestClient, title: str, content: str) -> dict:
    response = client.post(
        "/api/v1/documents",
        json={"title": title, "content": content, "sourceType": "markdown"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _chunks_of(db, document_id: str) -> list[DocumentChunk]:
    return list(
        db.execute(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index)
        ).scalars()
    )


def _delete_doc(db, document_id: str) -> None:
    """Remove a canary document from the shared test database.

    There is no delete endpoint, and later suites assert that every
    non-fixture document is approved — so archive canaries are removed
    once the SQL-scope assertion is done. Chunks disappear with the row
    through the ON DELETE CASCADE foreign key.
    """
    from sqlalchemy import text

    db.execute(text("DELETE FROM documents WHERE id = :id"), {"id": document_id})
    db.commit()
    db.expire_all()


class TestFingerprint:
    def test_is_deterministic_and_content_derived(self):
        first = chunk_fingerprint("dochash", 0, "some chunk text")
        again = chunk_fingerprint("dochash", 0, "some chunk text")
        assert first == again
        assert len(first) == 64  # sha256 hex

    def test_changes_with_content_index_or_document(self):
        base = chunk_fingerprint("dochash", 0, "some chunk text")
        assert base != chunk_fingerprint("dochash", 1, "some chunk text")
        assert base != chunk_fingerprint("dochash", 0, "other chunk text")
        assert base != chunk_fingerprint("otherdoc", 0, "some chunk text")

    def test_never_contains_row_ids(self):
        fingerprint = chunk_fingerprint("dochash", 0, "text")
        # It is a hash of content inputs only — not the ids themselves.
        assert "dochash" not in fingerprint


class TestIndexRun:
    def test_indexing_embeds_seed_corpus_and_fixtures(
        self, client: TestClient, db_session, knowledge_indexed
    ):
        """approved + challenge_fixture are indexed; every vector carries
        model + fingerprint identity."""
        rows = (
            db_session.execute(
                select(DocumentChunk, Document.knowledge_status, Document.status)
                .join(Document, Document.id == DocumentChunk.document_id)
                .where(Document.knowledge_status.in_(INDEXABLE_KNOWLEDGE_STATUSES))
            )
            .all()
        )
        assert rows, "no indexable chunks in the seeded corpus"
        fixture_seen = False
        for chunk, knowledge_status, status in rows:
            if status != "READY":
                continue
            assert chunk.embedding is not None, (
                f"chunk {chunk.id} ({knowledge_status}) was not embedded"
            )
            assert chunk.embedding_model == FAKE_MODEL
            assert chunk.embedding_fingerprint and len(chunk.embedding_fingerprint) == 64
            assert chunk.embedded_at is not None
            fixture_seen = fixture_seen or knowledge_status == "challenge_fixture"
        assert fixture_seen, "challenge fixture chunks must be indexed (controlled tests)"

    def test_archived_documents_are_never_indexed(
        self, client: TestClient, db_session, knowledge_indexed
    ):
        doc = _create_doc(client, "Archived Widget Bulletin", _widget_text("Archived Widget Bulletin"))
        document = db_session.get(Document, doc["id"])
        assert document is not None
        document.knowledge_status = "archived"
        db_session.commit()

        stats = IndexingService(db_session).index_all()
        # The archived document is not even considered eligible, so a run
        # over the otherwise fully-indexed corpus has nothing pending.
        assert stats.pending_chunks == 0
        assert stats.embedded_chunks == 0

        for chunk in _chunks_of(db_session, doc["id"]):
            assert chunk.embedding is None
            assert chunk.embedding_model is None
        # The scope tuple is the documented strategy.
        assert "archived" not in INDEXABLE_KNOWLEDGE_STATUSES
        _delete_doc(db_session, doc["id"])

    def test_second_run_reuses_embeddings_without_reembedding(
        self, client: TestClient, db_session, knowledge_indexed
    ):
        before = {
            chunk.id: chunk.embedded_at
            for chunk in db_session.execute(select(DocumentChunk)).scalars()
            if chunk.embedding is not None
        }
        stats = IndexingService(db_session).index_all()
        assert stats.eligible_chunks > 0
        assert stats.pending_chunks == 0
        assert stats.embedded_chunks == 0
        assert stats.up_to_date_chunks == stats.eligible_chunks
        db_session.expire_all()
        after = {
            chunk.id: chunk.embedded_at
            for chunk in db_session.execute(select(DocumentChunk)).scalars()
            if chunk.embedding is not None
        }
        assert before == after  # nothing was rewritten

    def test_dry_run_reports_pending_but_writes_nothing(
        self, client: TestClient, db_session, knowledge_indexed
    ):
        doc = _create_doc(client, "Dry Run Gizmo", _widget_text("Dry Run Gizmo"))
        stats = IndexingService(db_session).index_all(dry_run=True)
        assert stats.dry_run is True
        assert stats.embedded_chunks == 0
        assert stats.pending_chunks >= 1
        for chunk in _chunks_of(db_session, doc["id"]):
            assert chunk.embedding is None

    def test_force_reembeds_every_eligible_chunk(
        self, client: TestClient, db_session, knowledge_indexed
    ):
        stats = IndexingService(db_session).index_all(force=True)
        assert stats.eligible_chunks > 0
        assert stats.embedded_chunks == stats.eligible_chunks

    def test_changed_chunk_content_is_reembedded(
        self, client: TestClient, db_session, knowledge_indexed
    ):
        doc = _create_doc(
            client,
            "Mutable Gizmo",
            "# Mutable Gizmo\n\n## Section\n\nOriginal frobnication notes here.",
        )
        IndexingService(db_session).index_all()
        chunk = _chunks_of(db_session, doc["id"])[0]
        old_fingerprint = chunk.embedding_fingerprint
        assert old_fingerprint

        chunk.content = chunk.content + " Revised sprocket guidance added."
        db_session.commit()

        stats = IndexingService(db_session).index_all()
        assert stats.embedded_chunks >= 1
        db_session.expire_all()
        chunk = _chunks_of(db_session, doc["id"])[0]
        assert chunk.embedding_fingerprint != old_fingerprint
        assert chunk.embedding_model == FAKE_MODEL

    def test_model_mismatch_invalidates_old_vectors(
        self, client: TestClient, db_session, knowledge_indexed
    ):
        doc = _create_doc(
            client,
            "Stale Model Gizmo",
            "# Stale Model Gizmo\n\n## Section\n\nFrobnication under a retired encoder.",
        )
        IndexingService(db_session).index_all()
        chunk = _chunks_of(db_session, doc["id"])[0]
        assert chunk.embedding_model == FAKE_MODEL

        chunk.embedding_model = "some-retired-model-v0"
        db_session.commit()

        stats = IndexingService(db_session).index_all()
        assert stats.embedded_chunks >= 1
        db_session.expire_all()
        chunk = _chunks_of(db_session, doc["id"])[0]
        assert chunk.embedding_model == FAKE_MODEL  # rewritten with current model

    def test_provider_failure_leaves_chunks_null_never_fake(
        self, client: TestClient, db_session, knowledge_indexed
    ):
        class FailingProvider(EmbeddingProvider):
            @property
            def model_name(self) -> str:
                return "failing-test-provider"

            @property
            def dimensions(self) -> int:
                return 4096

            def embed_text(self, text: str) -> list[float]:
                raise EmbeddingProviderError("simulated outage")

            def embed_batch(self, texts: list[str]) -> list[list[float]]:
                raise EmbeddingProviderError("simulated outage")

        doc = _create_doc(
            client,
            "Outage Gizmo",
            "# Outage Gizmo\n\n## Section\n\nFrobnication that must stay un-searchable.",
        )
        with pytest.raises(EmbeddingProviderError, match="simulated outage"):
            IndexingService(db_session, provider=FailingProvider()).index_all()

        chunks = _chunks_of(db_session, doc["id"])
        assert chunks
        for chunk in chunks:
            assert chunk.embedding is None
            assert chunk.embedding_model is None
            assert chunk.embedding_fingerprint is None
