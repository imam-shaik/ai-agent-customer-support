"""Diagnostic: capture the RAW generation-task completion from the live
provider using the exact same prompts the agent uses. Read-only."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.llm import CompletionRequest, get_llm_provider
from app.llm.base import TASK_GENERATION
from app.llm.prompting import build_system_prompt, render_user_prompt
from app.services.evidence_context import build_evidence
from app.services.retrieval_service import RetrievalService

settings = get_settings()
provider = get_llm_provider(settings)
print(f"model: {provider.model_name}")

question = "How do I reset my password?"
with SessionLocal() as db:
    retrieval = RetrievalService(db).retrieve(query=question)

evidence = build_evidence(
    retrieval.candidates,
    max_items=settings.llm_max_evidence,
    max_chars=settings.llm_evidence_max_chars,
)
print(f"evidence items: {len(evidence)}")

request = CompletionRequest(
    system_prompt=build_system_prompt(TASK_GENERATION),
    question=question,
    evidence=evidence,
    task=TASK_GENERATION,
    context=(),
    candidate_answer=None,
    user_prompt=render_user_prompt(question, evidence),
)

raw = provider.complete(request)
print("--- RAW COMPLETION START ---")
print(raw[:3000])
print("--- RAW COMPLETION END ---")

try:
    parsed = json.loads(raw)
    print("json.loads: OK, keys =", list(parsed.keys()))
except json.JSONDecodeError as exc:
    print(f"json.loads: FAILED — {exc}")
