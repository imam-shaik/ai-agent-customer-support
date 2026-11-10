"""Test bootstrap (Phase 7).

Environment and an ISOLATED PostgreSQL + pgvector cluster are configured
BEFORE any app import, so settings and the engine point at a fresh test
database:

- The cluster lives in backend/data/pg-test and is provided by `pgserver`
  (PostgreSQL 16.2 + pgvector binaries bundled in the wheel) — no Docker,
  no external services, and no shared state with the development database
  (backend/data/pg). pgserver stops the cluster when pytest exits.
- The test database is dropped and recreated per session, then the schema
  is created from the models (Base.metadata.create_all), so every session
  starts from the same clean state.
- EMBEDDING_PROVIDER=fake + LLM_PROVIDER=stub: the deterministic TEST
  providers — allowed here because ENVIRONMENT=testing, and the reason
  the automated suite never needs an API key. No runtime override can
  attach them outside the suite.
"""

import os
import sys
from pathlib import Path

# Make `app` importable regardless of where pytest is invoked from.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_BACKEND_DIR = Path(__file__).resolve().parents[1]
_TEST_PGDATA = _BACKEND_DIR / "data" / "pg-test"
_TEST_DATABASE = "vilasat_test"

os.environ["ENVIRONMENT"] = "testing"
os.environ["LOG_LEVEL"] = "WARNING"
os.environ["EMBEDDING_PROVIDER"] = "fake"
# The deterministic TEST LLM. Pinned explicitly (not inherited from
# backend/.env, which configures the real nvidia provider) so the suite
# stays hermetic: ENVIRONMENT=testing is what makes the stub reachable.
os.environ["LLM_PROVIDER"] = "stub"
# Hermetic from the developer's backend/.env: real keys must never reach
# the suite (they would flip /health to "live" and break honest-mode
# assertions). Empty string = "not configured" for every provider guard.
os.environ["EMBEDDING_API_KEY"] = ""
os.environ["NVIDIA_API_KEY"] = ""
# The fake provider's vector contract must also be hermetic: live role
# prefixes ("query: "/"passage: ") would leak into the lexical fake
# vectors and shift every similarity, and the dimension must match the
# migrated schema (vector(2048)) for the factory's dimension guard.
os.environ["EMBEDDING_QUERY_PREFIX"] = ""
os.environ["EMBEDDING_PASSAGE_PREFIX"] = ""
os.environ["EMBEDDING_DIMENSIONS"] = "4096"
# Staff reply email dispatch must also be hermetic: a developer's
# backend/.env must never make tests send real email (and the honest
# not-configured state is what the reply tests assert).
os.environ["SMTP_HOST"] = ""
os.environ["SMTP_USERNAME"] = ""
os.environ["SMTP_PASSWORD"] = ""
os.environ["SMTP_FROM"] = ""
# Demo/Live mode is persisted in a file; keep the suite hermetic and
# reset it to Live for every test (demo-mode tests switch explicitly).
_PROVIDER_MODE_FILE = _BACKEND_DIR / "data" / "provider-mode-test.json"
_PROVIDER_MODE_FILE.unlink(missing_ok=True)
os.environ["PROVIDER_MODE_FILE"] = str(_PROVIDER_MODE_FILE)


def _prepare_test_database() -> str:
    """Start (or attach to) the test cluster; return a fresh database URL."""
    import pgserver
    import psycopg

    # First use initializes the cluster; pgserver registers an atexit hook
    # that shuts it down when the last pytest process finishes.
    server = pgserver.get_server(str(_TEST_PGDATA))
    maintenance_url = server.get_uri()  # postgresql://postgres@host:port/postgres

    with psycopg.connect(maintenance_url, autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{_TEST_DATABASE}" WITH (FORCE)')
        conn.execute(f'CREATE DATABASE "{_TEST_DATABASE}"')

    base_url = maintenance_url.rsplit("/", 1)[0]
    test_url = f"{base_url}/{_TEST_DATABASE}"
    with psycopg.connect(test_url) as conn:
        # Required before any vector(1024) column can be created.
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    return test_url.replace("postgresql://", "postgresql+psycopg://", 1)


os.environ["DATABASE_URL"] = _prepare_test_database()

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="session")
def client() -> TestClient:
    from app.db.session import engine
    from app.main import app
    from app.models import Base

    Base.metadata.create_all(engine)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def reset_provider_mode():
    """Every test starts and ends in Live mode."""
    from app.services.provider_mode_service import set_mode

    set_mode("live")
    try:
        yield
    finally:
        set_mode("live")


@pytest.fixture(autouse=True)
def staff_auth_bypass():
    """Admin escalation endpoints require a staff session; the existing
    suite exercises them without one. Override the dependency for every
    test — test_auth.py removes the override to exercise the real
    register/login/verify flow. Restored after each test.
    """
    from app.api.deps import get_current_staff
    from app.main import app
    from app.models.entities import StaffUser

    fake_staff = StaffUser(
        id="test-staff-user",
        name="Test Staff",
        email="test-staff@example.com",
        password_hash="not-a-real-hash",
    )
    app.dependency_overrides[get_current_staff] = lambda: fake_staff
    yield
    app.dependency_overrides.pop(get_current_staff, None)


@pytest.fixture()
def db_session():
    from app.db.session import SessionLocal

    with SessionLocal() as session:
        yield session


@pytest.fixture(scope="session", autouse=True)
def knowledge_indexed(client: TestClient) -> None:
    """Index the seeded knowledge corpus once per session (fake provider).

    Phase 8A: the chat pipeline retrieves evidence on EVERY turn, so the
    corpus must be embedded before any test runs (autouse). Retrieval-
    quality tests depend on the 8 seeded knowledge documents; indexing
    stays explicit in the application (never automatic) — tests opt in
    through this fixture.
    """
    from app.db.session import SessionLocal
    from app.services.indexing_service import IndexingService

    with SessionLocal() as db:
        stats = IndexingService(db).index_all()
    assert stats.embedded_chunks > 0, "seed corpus produced no chunks to index"


@pytest.fixture()
def conversation_with_message(client: TestClient) -> dict:
    """A conversation containing one customer message (escalation precondition)."""
    session = client.post("/api/v1/chat/sessions", json={}).json()
    conversation_id = session["conversationId"]
    client.post(
        f"/api/v1/chat/sessions/{conversation_id}/messages",
        json={"content": "How do I reset my password?"},
    )
    return {"conversationId": conversation_id}
