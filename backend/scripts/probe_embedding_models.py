"""One-off probe: compare embedding-model candidates against the real corpus.

For each candidate model, embed 4 corpus passages + 4 customer questions and
measure whether the CORRECT passage ranks first and by what margin over the
best wrong passage. Read-only; prints a compact table and exits.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx  # noqa: E402

from app.core.config import get_settings  # noqa: E402


def embed(
    client: httpx.Client,
    model: str,
    texts: list[str],
    input_type: str | None = None,
):
    """Embed items one-by-one: the endpoint 500s on larger batches for the
    asymmetric 3.5 models, and single-item calls are reliable everywhere."""
    vectors: list[list[float]] = []
    for text in texts:
        payload = {"model": model, "input": [text], "encoding_format": "float"}
        if input_type:
            payload["input_type"] = input_type
        response = client.post("/embeddings", json=payload)
        if response.status_code != 200:
            return None, f"HTTP {response.status_code}: {(response.text or '')[:80]}"
        data = sorted(response.json()["data"], key=lambda row: row.get("index", 0))
        vectors.append(data[0]["embedding"])
    return vectors, None


def cos(a: list[float], b: list[float]) -> float:
    num = sum(x * y for x, y in zip(a, b))
    da = math.sqrt(sum(x * x for x in a))
    db = math.sqrt(sum(x * x for x in b))
    return num / (da * db) if da and db else 0.0


PASSAGES = [
    ("acct", "On the sign-in page, select Forgot password?, enter your workspace "
             "email, and we send a reset link that is valid for 30 minutes."),
    ("billing", "If a renewal charge is declined, we email the billing contact "
                "and retry the same card after 3 days and again after 7 days."),
    ("sso", "Enterprise plans can connect a SAML 2.0 identity provider from "
            "Settings, and once SSO is enforced, members authenticate through "
            "your identity provider."),
    ("hooks", "Outgoing webhooks deliver ticket and conversation events to your "
              "endpoint over HTTPS with a signing secret. Failed deliveries "
              "retry with backoff for up to 24 hours."),
]

QUERIES = [
    ("q-password", "How do I reset my password?", "acct"),
    ("q-cardfail", "What happens if my card payment fails?", "billing"),
    ("q-sso", "Do you support SAML single sign-on?", "sso"),
    ("q-hooks", "How do webhook retries work?", "hooks"),
]

MODELS = [
    "nvidia/nemotron-3-embed-1b",       # current (flat band, baseline)
    "nvidia/nemotron-3.5-embed-1b",     # asymmetric: input_type required
    "nvidia/nemotron-3.5-embed-8b",     # asymmetric: input_type required
]

# The asymmetric 3.5 models require input_type per call; the symmetric
# baseline must not receive one.
ASYMMETRIC = {
    "nvidia/nemotron-3.5-embed-1b": ("query", "passage"),
    "nvidia/nemotron-3.5-embed-8b": ("query", "passage"),
}


def main() -> int:
    settings = get_settings()
    client = httpx.Client(
        base_url=settings.embedding_base_url.rstrip("/"),
        headers={"Authorization": f"Bearer {settings.embedding_api_key or ''}"},
        timeout=60,
    )
    print(f"{'model':<48} {'dim':>5} {'top1':>4} {'avgMargin':>9}")
    for model in MODELS:
        q_type, p_type = ASYMMETRIC.get(model, (None, None))
        vectors, error = embed(
            client, model, [text for _, text in PASSAGES], input_type=p_type
        )
        if error:
            print(f"{model:<48}  ERR  {error}")
            continue
        query_vectors, error = embed(
            client, model, [text for _, text, _ in QUERIES], input_type=q_type
        )
        if error:
            print(f"{model:<48}  ERR  {error}")
            continue
        top1 = 0
        margins: list[float] = []
        for index, (_, _, expected) in enumerate(QUERIES):
            scored = sorted(
                (
                    (cos(query_vectors[index], pv), key)
                    for (key, _), pv in zip(PASSAGES, vectors)
                ),
                reverse=True,
            )
            if scored[0][1] == expected:
                top1 += 1
            wrong = max(score for score, key in scored if key != expected)
            margins.append(scored[0][0] - wrong)
        dims = len(query_vectors[0])
        print(f"{model:<48} {dims:>5} {top1}/4 {sum(margins)/len(margins):>9.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
