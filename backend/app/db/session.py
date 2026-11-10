"""Engine/session wiring.

Phase 7: PostgreSQL + pgvector is the only supported database (semantic
search needs the native `vector` type). The engine is still built purely
from Settings.database_url, so the connection itself stays environment-
driven — no credentials in code.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

engine = create_engine(settings.database_url, future=True, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: one session per request, always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
