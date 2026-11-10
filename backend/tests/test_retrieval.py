"""Retrieval tests (Phase 7 §15).

Retrieval finds POSSIBLE EVIDENCE only — these tests never assert that an
answer was produced, and several of them explicitly assert that no answer
or sufficiency field exists anywhere in the contract.

Ranking assertions use the deterministic fake provider (lexical overlap),
so queries are phrased with meaningfully different wording but shared
vocabulary, and target documents are verified by exact title rather than
by generic "some result" checks.
"""

import dataclasses

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text, update

from app.core.exceptions import InvalidInputError
from app.embeddings import EmbeddingProviderError
from app.models.entities import Document, DocumentChunk
from app.services.indexing_service import IndexingService
from app.services.retrieval_service import RetrievalService

FIXTURE_QUERY = "legacy platform migration retention notice"
FIXTURE_TITLE = "Legacy Retention Notice (Challenge Fixture)"


def _delete_doc(db, document_id: str) -> None:
    """Remove a canary document from the shared test database (no delete
    endpoint exists; chunks follow via ON DELETE CASCADE)."""
    from sqlalchemy import text

    db.execute(text("DELETE FROM documents WHERE id = :id"), {"id": document_id})
    db.commit()
    db.expire_all()


def _create_doc(client: TestClient, title: str, content: str) -> dict:
    response = client.post(
        "/api/v1/documents",
        json={"title": title, "content": content, "sourceType": "markdown"},
    )
    assert response.status_code == 201, response.text
    return response.json()


class TestSemanticRanking:
    def test_password_query_returns_account_access_first(
        self, db_session, knowledge_indexed
    ):
        # The canonical documented question: with the fake lexical-hash
        # provider (2048 buckets) it ranks the Account Access chunk first
        # by clear shared-vocabulary margin.
        result = RetrievalService(db_session).retrieve(
            query="How do I reset my password?"
        )
        assert result.candidates
        top = result.candidates[0]
        assert top.document_title == "Account Access & Recovery"
        assert "Password" in top.section_title or "password" in top.content.lower()
        # Approved knowledge only — the SQL scope, not a post-filter.
        assert all(c.knowledge_status == "approved" for c in result.candidates)

    def test_billing_query_returns_billing_document(
        self, db_session, knowledge_indexed
    ):
        result = RetrievalService(db_session).retrieve(
            query="When am I charged for my plan and how do I download my invoice"
        )
        top_titles = [c.document_title for c in result.candidates[:3]]
        assert "Billing & Subscription Plans" in top_titles

    def test_seats_query_returns_subscription_document(
        self, db_session, knowledge_indexed
    ):
        result = RetrievalService(db_session).retrieve(
            query="what happens when seats are added mid-cycle"
        )
        top_titles = [c.document_title for c in result.candidates[:3]]
        assert "Managing Your Subscription" in top_titles

    def test_results_are_ordered_and_scores_are_exact(
        self, db_session, knowledge_indexed
    ):
        result = RetrievalService(db_session).retrieve(query="password reset link")
        assert result.candidates
        distances = [c.cosine_distance for c in result.candidates]
        assert distances == sorted(distances)
        for candidate in result.candidates:
            # Exact identity, not a rescaling — and honest bounds.
            assert candidate.cosine_similarity == 1.0 - candidate.cosine_distance
            assert -1.0 <= candidate.cosine_similarity <= 1.0
            assert candidate.cosine_distance >= 0.0
        assert result.embedding_model == "fake-lexical-hash-v1"
        assert result.limit == 5  # configured default, not a magic number


class TestUnsupportedQuery:
    def test_returns_candidates_only_never_an_answer(
        self, db_session, knowledge_indexed
    ):
        result = RetrievalService(db_session).retrieve(
            query="quantum chromodynamics lattice gauge theory"
        )
        # Weak matches stay visible as candidates (threshold default 0.0);
        # deciding whether evidence is sufficient is NOT retrieval's job.
        assert result.candidates
        allowed = {
            "chunk_id",
            "document_id",
            "document_title",
            "section_id",
            "section_title",
            "chunk_index",
            "content",
            "knowledge_status",
            "source",
            "cosine_distance",
            "cosine_similarity",
        }
        for candidate in result.candidates:
            assert {f.name for f in dataclasses.fields(candidate)} == allowed
        assert all(c.cosine_similarity < 0.5 for c in result.candidates)


class TestKnowledgeStatusScope:
    def test_normal_retrieval_never_returns_challenge_fixtures(
        self, db_session, knowledge_indexed
    ):
        # The fixture shares vocabulary with the real retention policy and
        # would rank high lexically — exclusion must come from the query.
        result = RetrievalService(db_session).retrieve(query=FIXTURE_QUERY, limit=20)
        assert result.candidates
        assert all(c.knowledge_status != "challenge_fixture" for c in result.candidates)

    def test_fixtures_reachable_only_via_explicit_service_flag(
        self, db_session, knowledge_indexed
    ):
        result = RetrievalService(db_session).retrieve(
            query=FIXTURE_QUERY, limit=20, include_challenge_fixtures=True
        )
        assert result.include_challenge_fixtures is True
        fixture_candidates = [
            c for c in result.candidates if c.knowledge_status == "challenge_fixture"
        ]
        assert fixture_candidates, "flagged retrieval must surface the fixture"
        assert any(c.document_title == FIXTURE_TITLE for c in fixture_candidates)

    def test_archived_document_is_excluded_by_the_sql_scope(
        self, client: TestClient, db_session, knowledge_indexed
    ):
        doc = _create_doc(
            client,
            "Archived Retrieval Canary",
            "# Archived Retrieval Canary\n\n## Section\n\n"
            "The zorbulon bulletin is retained only for this retrieval test.",
        )
        IndexingService(db_session).index_all()

        before = RetrievalService(db_session).retrieve(query="zorbulon", limit=20)
        assert any(c.document_id == doc["id"] for c in before.candidates)

        db_session.execute(
            update(Document)
            .where(Document.id == doc["id"])
            .values(knowledge_status="archived")
        )
        db_session.commit()

        after = RetrievalService(db_session).retrieve(query="zorbulon", limit=20)
        assert after.candidates  # other rows still returned
        assert all(c.document_id != doc["id"] for c in after.candidates)
        _delete_doc(db_session, doc["id"])

    def test_vectors_from_a_different_model_are_never_searched(
        self, client: TestClient, db_session, knowledge_indexed
    ):
        doc = _create_doc(
            client,
            "Retired Encoder Canary",
            "# Retired Encoder Canary\n\n## Section\n\n"
            "The frobnox indicator belongs to the retired encoder test.",
        )
        IndexingService(db_session).index_all()

        before = RetrievalService(db_session).retrieve(query="frobnox", limit=20)
        assert any(c.document_id == doc["id"] for c in before.candidates)

        chunks = list(
            db_session.execute(
                select(DocumentChunk).where(DocumentChunk.document_id == doc["id"])
            ).scalars()
        )
        for chunk in chunks:
            chunk.embedding_model = "retired-model-v0"
        db_session.commit()

        after = RetrievalService(db_session).retrieve(query="frobnox", limit=20)
        assert all(c.document_id != doc["id"] for c in after.candidates)


class TestServiceValidation:
    def test_empty_and_whitespace_queries_rejected(self, db_session, knowledge_indexed):
        with pytest.raises(InvalidInputError):
            RetrievalService(db_session).retrieve(query="")
        with pytest.raises(InvalidInputError):
            RetrievalService(db_session).retrieve(query="   ")

    def test_overlong_query_rejected_before_embedding(
        self, db_session, knowledge_indexed
    ):
        with pytest.raises(InvalidInputError, match="2000"):
            RetrievalService(db_session).retrieve(query="a" * 2001)

    @pytest.mark.parametrize("limit", [0, -1, 21, 999])
    def test_limits_outside_config_range_rejected(
        self, db_session, knowledge_indexed, limit: int
    ):
        with pytest.raises(InvalidInputError, match="limit"):
            RetrievalService(db_session).retrieve(query="password", limit=limit)

    def test_invalid_queries_never_reach_the_embedding_provider(
        self, db_session, knowledge_indexed, monkeypatch
    ):
        import app.services.retrieval_service as retrieval_module
        from app.embeddings.fake import FakeEmbeddingProvider

        class SpyProvider(FakeEmbeddingProvider):
            def __init__(self) -> None:
                super().__init__(dimensions=2048)
                self.embed_calls: list[str] = []

            def embed_text(self, text: str) -> list[float]:
                self.embed_calls.append(text)
                return super().embed_text(text)

        spy = SpyProvider()
        monkeypatch.setattr(
            retrieval_module, "get_embedding_provider", lambda settings=None: spy
        )

        with pytest.raises(InvalidInputError):
            RetrievalService(db_session).retrieve(query="")
        with pytest.raises(InvalidInputError):
            RetrievalService(db_session).retrieve(query="a" * 2001)
        with pytest.raises(InvalidInputError):
            RetrievalService(db_session).retrieve(query="password", limit=999)

        assert spy.embed_calls == []  # validation precedes any embedding call


class TestHttpContract:
    def test_search_returns_structured_candidates_only(
        self, client: TestClient, knowledge_indexed
    ):
        response = client.post(
            "/api/v1/retrieval/search", json={"query": "How do I reset my password?"}
        )
        assert response.status_code == 200
        body = response.json()
        assert set(body) == {
            "embeddingModel",
            "limit",
            "minCosineSimilarity",
            "candidateCount",
            "candidates",
        }
        assert body["embeddingModel"] == "fake-lexical-hash-v1"
        assert body["candidateCount"] == len(body["candidates"]) > 0
        # No answer, no sufficiency signal — anywhere.
        assert "answer" not in body and "sufficient" not in body
        candidate = body["candidates"][0]
        assert set(candidate) == {
            "chunkId",
            "documentId",
            "documentTitle",
            "sectionId",
            "sectionTitle",
            "chunkIndex",
            "content",
            "knowledgeStatus",
            "source",
            "cosineDistance",
            "cosineSimilarity",
        }
        assert candidate["knowledgeStatus"] == "approved"
        assert candidate["cosineSimilarity"] == 1.0 - candidate["cosineDistance"]
        assert "answer" not in candidate and "sufficient" not in candidate

    @pytest.mark.parametrize(
        "payload",
        [
            {"query": ""},
            {"query": "   "},
            {"query": "a" * 2001},
            {"query": "password", "limit": 0},
            {"query": "password", "limit": 999},
            {"query": "password", "limit": -1},
        ],
        ids=["empty", "whitespace", "overlong", "limit-zero", "limit-too-big", "limit-negative"],
    )
    def test_invalid_payloads_are_rejected_with_the_error_envelope(
        self, client: TestClient, knowledge_indexed, payload: dict
    ):
        response = client.post("/api/v1/retrieval/search", json=payload)
        assert response.status_code == 422
        error = response.json()["error"]
        assert error["code"] == "VALIDATION_ERROR"
        assert error["request_id"]  # every error carries the correlation id

    def test_challenge_fixture_flag_is_impossible_over_http(
        self, client: TestClient, knowledge_indexed
    ):
        response = client.post(
            "/api/v1/retrieval/search",
            json={
                "query": FIXTURE_QUERY,
                "limit": 20,
                "includeChallengeFixtures": True,
            },
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    def test_provider_failure_returns_explicit_503(
        self, client: TestClient, monkeypatch
    ):
        import app.services.retrieval_service as retrieval_module

        def _boom(settings=None):
            raise EmbeddingProviderError(
                "EMBEDDING_API_KEY is not configured; set it to enable real embeddings"
            )

        monkeypatch.setattr(retrieval_module, "get_embedding_provider", _boom)
        response = client.post(
            "/api/v1/retrieval/search", json={"query": "password reset"}
        )
        assert response.status_code == 503
        error = response.json()["error"]
        assert error["code"] == "EMBEDDING_PROVIDER_UNAVAILABLE"
        assert "EMBEDDING_API_KEY" in error["message"]


class TestVectorSchema:
    def test_native_vector_column_2048_and_no_hnsw_at_this_width(
        self, db_session, knowledge_indexed
    ):
        # pgvector's HNSW index caps at 2000 dimensions, so vector(2048)
        # (nemotron-3-embed-1b) cannot be HNSW-indexed. At MVP corpus scale
        # the exact sequential cosine scan is correct and fast, so no ANN
        # index exists on the column. Revisit (halfvec expression index or a
        # <=2000-dim model) only if the corpus grows enough to need it.
        index_row = db_session.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE tablename = 'document_chunks' "
                "AND indexname = 'ix_document_chunks_embedding_hnsw'"
            )
        ).fetchone()
        assert index_row is None  # HNSW deliberately absent at 2048 dims

        column_row = db_session.execute(
            text(
                "SELECT format_type(a.atttypid, a.atttypmod) FROM pg_attribute a "
                "WHERE a.attrelid = 'document_chunks'::regclass "
                "AND a.attname = 'embedding' AND NOT a.attisdropped"
            )
        ).fetchone()
        assert column_row is not None
        assert column_row[0] == "vector(2048)"  # native pgvector type, not JSON

        extension_row = db_session.execute(
            text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        ).fetchone()
        assert extension_row is not None
