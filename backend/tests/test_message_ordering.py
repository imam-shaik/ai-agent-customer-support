"""Transcript ordering under clock ties (regression test).

Root cause fixed in `app/models/entities.py::_now`: on Windows (Python
<= 3.12) the wall clock ticks at ~15.6 ms, so the customer message and
its assistant reply of one turn could share a timestamp — and every
transcript is ordered by `created_at`, which made the order unstable
(a reload could show the reply before the question; the tie also
flipped inside the test suite itself).

`_now` is now strictly monotonic (1 microsecond bump inside a frozen
tick). These tests pin that behavior: with the clock FORCED to stand
still — the exact defect condition — a turn's transcript must still be
chronological everywhere it is read (history endpoint, staff detail,
and the conversation relationship).
"""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from app.models import entities as model_entities


def _turn(client: TestClient, conversation_id: str) -> None:
    response = client.post(
        f"/api/v1/chat/sessions/{conversation_id}/messages",
        json={"content": "How do I reset my password?"},
    )
    assert response.status_code == 200


class TestTranscriptOrderUnderClockTies:
    def test_history_is_chronological_when_the_clock_is_frozen(
        self, client: TestClient, monkeypatch
    ):
        class _FrozenClock:
            """Stands in for the time module with a frozen time_ns()."""

            def __init__(self, ns: int) -> None:
                self._ns = ns

            def time_ns(self) -> int:
                return self._ns

        frozen = time.time_ns()
        monkeypatch.setattr(model_entities, "time", _FrozenClock(frozen))

        session = client.post("/api/v1/chat/sessions", json={}).json()
        conversation_id = session["conversationId"]
        _turn(client, conversation_id)

        history = client.get(
            f"/api/v1/chat/sessions/{conversation_id}/messages"
        ).json()
        roles = [message["role"] for message in history["messages"]]
        assert roles == ["user", "assistant"]

    def test_monotonic_clock_never_repeats_or_goes_backwards(self, monkeypatch):
        class _FrozenClock:
            def __init__(self, ns: int) -> None:
                self._ns = ns

            def time_ns(self) -> int:
                return self._ns

        frozen = 1_700_000_000_000_000_000  # nanoseconds
        monkeypatch.setattr(model_entities, "time", _FrozenClock(frozen))

        stamps = [model_entities._now() for _ in range(50)]
        micros = [int(s.timestamp() * 1_000_000) for s in stamps]
        assert micros == sorted(micros)
        assert len(set(micros)) == len(micros)  # strictly increasing: no ties
