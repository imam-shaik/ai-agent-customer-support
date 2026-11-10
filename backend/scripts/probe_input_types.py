"""Discover the valid input_type values for the asymmetric embed models."""

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

for value in ["query", "passage", "text", "doc", "document", "image",
              "Query", "Passage", "query_text", "passage_text"]:
    response = client.post(
        "/embeddings",
        json={
            "model": "nvidia/nemotron-3.5-embed-1b",
            "input": ["hello world"],
            "encoding_format": "float",
            "input_type": value,
        },
    )
    if response.status_code == 200:
        dims = len(response.json()["data"][0]["embedding"])
        detail = f"OK dims={dims}"
    else:
        detail = (response.text or "")[:100]
    print(f"{value:<14} -> {response.status_code} {detail}")
