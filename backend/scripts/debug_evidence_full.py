"""Print the FULL evidence text for one question (verification)."""

import io
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.evidence_context import build_evidence
from app.services.retrieval_service import RetrievalService

question = sys.argv[1] if len(sys.argv) > 1 else "How do I invite my team?"
settings = get_settings()

with SessionLocal() as db:
    retrieval = RetrievalService(db).retrieve(query=question)
evidence = build_evidence(
    retrieval.candidates,
    max_items=settings.llm_max_evidence,
    max_chars=settings.llm_evidence_max_chars,
)
for item in evidence:
    print(f"--- [{item.ref}] {item.document_title} > {item.section_title} ---")
    print(item.content)
    print()
