"""Bisect the nemotron-3.5-embed batch failure: batch size? specific text?"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

from app.core.config import get_settings  # noqa: E402

settings = get_settings()
client = httpx.Client(
    base_url=settings.embedding_base_url.rstrip("/"),
    headers={"Authorization": f"Bearer {settings.embedding_api_key or ''}"},
    timeout=60,
)

TEXTS = [
    "On the sign-in page, select Forgot password?, enter your workspace "
    "email, and we send a reset link that is valid for 30 minutes.",
    "If a renewal charge is declined, we email the billing contact "
    "and retry the same card after 3 days and again after 7 days.",
    "Enterprise plans can connect a SAML 2.0 identity provider from "
    "Settings, and once SSO is enforced, members authenticate through "
    "your identity provider.",
    "Outgoing webhooks deliver ticket and conversation events to your "
    "endpoint over HTTPS with a signing secret. Failed deliveries "
    "retry with backoff for up to 24 hours.",
]


def try_embed(model: str, texts: list[str], input_type: str) -> str:
    response = client.post(
        "/embeddings",
        json={
            "model": model,
            "input": list(texts),
            "encoding_format": "float",
            "input_type": input_type,
        },
    )
    if response.status_code == 200:
        return f"OK ({len(response.json()['data'])} vectors)"
    return (response.text or "")[:90]


for model in ["nvidia/nemotron-3.5-embed-1b", "nvidia/nemotron-3.5-embed-8b"]:
    print(f"--- {model}")
    for size in (4, 3, 2, 1):
        print(f"  batch={size} passage: {try_embed(model, TEXTS[:size], 'passage')}")
    print(f"  batch=1 query  : {try_embed(model, ['How do I reset my password?'], 'query')}")
    # per-text isolation at batch=1 for the first failing size
    for index, text in enumerate(TEXTS):
        print(f"  single[{index}]        : {try_embed(model, [text], 'passage')}")
