#!/usr/bin/env python
"""Explicit knowledge indexing — embeds eligible chunks into pgvector.

This is the ONLY supported way to write embeddings (Phase 7 §8): never at
application startup, never during a search request. Safe to re-run: chunks
whose content fingerprint and model already match are skipped, so
unchanged content is never re-embedded.

Usage (from backend/, database must be running: scripts/dev_db.py start):
    python scripts/index_knowledge.py             # incremental (missing/stale only)
    python scripts/index_knowledge.py --force     # re-embed everything eligible
    python scripts/index_knowledge.py --dry-run   # report pending counts only

Exit codes: 0 success, 1 provider/config failure (affected chunks remain
un-searchable), 2 usage error.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.embeddings import EmbeddingProviderError  # noqa: E402


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--force",
        action="store_true",
        help="re-embed every eligible chunk even when its fingerprint matches",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report eligible/pending counts without calling the provider",
    )
    args = parser.parse_args(argv)

    from app.db.session import SessionLocal
    from app.services.indexing_service import IndexingService

    try:
        with SessionLocal() as db:
            stats = IndexingService(db).index_all(force=args.force, dry_run=args.dry_run)
    except EmbeddingProviderError as exc:
        # Config guidance only — never contains keys or raw HTTP detail.
        print(f"[index] FAILED: {exc}", file=sys.stderr)
        return 1

    verb = "would embed" if stats.dry_run else "embedded"
    print(
        f"[index] eligible={stats.eligible_chunks} pending={stats.pending_chunks} "
        f"up_to_date={stats.up_to_date_chunks} {verb}={stats.embedded_chunks} "
        f"batches={stats.batches}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
