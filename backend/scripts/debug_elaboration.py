"""Probe: how much does the live generation elaborate vs. copy evidence?

Runs retrieval + generation + support exactly like the agent and prints
evidence snippets, the raw answer, and the support verdict, so the
copy-vs-elaborate behavior is measurable before/after prompt changes.
"""

import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.llm import CompletionRequest, get_llm_provider
from app.llm.base import TASK_GENERATION, TASK_SUPPORT
from app.llm.prompting import (
    build_system_prompt,
    render_support_prompt,
    render_user_prompt,
)
from app.services.evidence_context import build_evidence
from app.services.retrieval_service import RetrievalService

QUESTIONS = sys.argv[1:] or [
    "How do I invite my team?",
    "How do I reset my password?",
]

settings = get_settings()
provider = get_llm_provider(settings)

for question in QUESTIONS:
    print("=" * 70)
    print(f"QUESTION: {question}")
    with SessionLocal() as db:
        retrieval = RetrievalService(db).retrieve(query=question)
    evidence = build_evidence(
        retrieval.candidates,
        max_items=settings.llm_max_evidence,
        max_chars=settings.llm_evidence_max_chars,
    )
    if not evidence:
        print("  (no evidence — skip)")
        continue

    print(f"  evidence: {len(evidence)} item(s)")
    for item in evidence:
        head = item.content[:150].replace("\n", " ")
        print(f"    [{item.ref}] {item.document_title} > {item.section_title}: {head}...")

    # --- generation ---
    raw = provider.complete(
        CompletionRequest(
            system_prompt=build_system_prompt(TASK_GENERATION),
            question=question,
            evidence=evidence,
            task=TASK_GENERATION,
            context=(),
            candidate_answer=None,
            user_prompt=render_user_prompt(question, evidence),
        )
    )
    print("  --- RAW GENERATION ---")
    print("  " + raw.replace("\n", "\n  ")[:1500])

    # --- support check on that answer ---
    try:
        answer = json.loads(raw)["answer"]
    except Exception:
        print("  (generation malformed — support check skipped)")
        continue
    verdict_raw = provider.complete(
        CompletionRequest(
            system_prompt=build_system_prompt(TASK_SUPPORT),
            question=question,
            evidence=evidence,
            task=TASK_SUPPORT,
            context=(),
            candidate_answer=answer,
            user_prompt=render_support_prompt(question, evidence, answer),
        )
    )
    print("  --- SUPPORT VERDICT ---")
    print("  " + verdict_raw[:300])
