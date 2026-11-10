"""Diagnostic: does a corrective re-ask fix the malformed generation?

Call the live provider exactly like the agent; when the first output is
malformed JSON, retry with an explicit corrective instruction and check
the result parses to the documented schema.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pydantic import ValidationError

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.llm import CompletionRequest, get_llm_provider
from app.llm.base import TASK_GENERATION
from app.llm.prompting import build_system_prompt, render_user_prompt
from app.schemas.agent import GroundedGeneration
from app.services.evidence_context import build_evidence
from app.services.retrieval_service import RetrievalService

CORRECTIVE = (
    "\n\nCRITICAL CORRECTION: your previous reply was REJECTED because it was "
    "not valid JSON — a string value was not closed before the next field. "
    "Reply AGAIN with the raw JSON object only, exactly in this shape: "
    '{"answer": "...", "citation_ids": ["E1"]} — every string value properly '
    "opened and closed, no double quote characters inside the answer text, "
    "and nothing after the closing brace. Your answer content can stay the "
    "same; only the JSON formatting needs to be correct."
)

QUESTIONS = [
    "How do I reset my password?",
    "When am I billed?",
    "Do you offer a mobile app for smart watches?",
    "My account isn't working",
]

settings = get_settings()
provider = get_llm_provider(settings)

for question in QUESTIONS:
    with SessionLocal() as db:
        retrieval = RetrievalService(db).retrieve(query=question)
    evidence = build_evidence(
        retrieval.candidates,
        max_items=settings.llm_max_evidence,
        max_chars=settings.llm_evidence_max_chars,
    )
    if not evidence:
        print(f"[{question[:30]}...] — no evidence (skip generation probe)")
        continue

    user_prompt = render_user_prompt(question, evidence)
    request = CompletionRequest(
        system_prompt=build_system_prompt(TASK_GENERATION),
        question=question,
        evidence=evidence,
        task=TASK_GENERATION,
        context=(),
        candidate_answer=None,
        user_prompt=user_prompt,
    )
    raw1 = provider.complete(request)
    try:
        data = json.loads(raw1)
        GroundedGeneration.model_validate(data)
        print(f"[{question[:30]}...] first try: OK")
        continue
    except (json.JSONDecodeError, ValidationError) as exc:
        first_error = f"{type(exc).__name__}: {str(exc)[:80]}"

    request2 = CompletionRequest(
        system_prompt=build_system_prompt(TASK_GENERATION),
        question=question,
        evidence=evidence,
        task=TASK_GENERATION,
        context=(),
        candidate_answer=None,
        user_prompt=user_prompt + CORRECTIVE,
    )
    raw2 = provider.complete(request2)
    try:
        data = json.loads(raw2)
        GroundedGeneration.model_validate(data)
        print(f"[{question[:30]}...] first: FAIL ({first_error}) -> corrective retry: OK")
    except (json.JSONDecodeError, ValidationError) as exc:
        print(f"[{question[:30]}...] first: FAIL ({first_error}) -> corrective retry: STILL FAIL ({type(exc).__name__})")
        print("   raw2 head:", raw2[:200].replace(chr(10), " "))
