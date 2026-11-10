#!/usr/bin/env python
"""Re-ingest knowledge files whose content changed on disk.

The startup seed is idempotent BY DESIGN: documents that already have
stored content are skipped, so editing a file in backend/knowledge/ does
not reach the development database by itself. This script closes that
gap: it compares each file's normalized content hash with the stored row
and re-ingests ONLY changed files — through the real pipeline (the same
`ingest_content` path the seed uses), never by direct DB writes.

Missing documents are created, changed documents are re-ingested (chunks
replaced), and up-to-date documents are left untouched. Run
scripts/index_knowledge.py afterwards so the new chunks get embeddings.

Usage (from backend/, database must be running: scripts/dev_db.py start):
    python scripts/update_knowledge.py             # apply changed files
    python scripts/update_knowledge.py --dry-run   # report without writing

Exit codes: 0 success (failures are reported per file), 2 usage error.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ingestion.pipeline import content_hash, normalize  # noqa: E402


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report which files changed without writing anything",
    )
    args = parser.parse_args(argv)

    from app.db.seed import _knowledge_files
    from app.db.session import SessionLocal
    from app.models import Document
    from app.schemas.document import DocumentCreate
    from app.services.document_service import DocumentService

    updated = created = unchanged = failed = 0

    with SessionLocal() as db:
        service = DocumentService(db)

        for path, knowledge_status in _knowledge_files():
            relative = path.relative_to(_knowledge_files_dir()).as_posix()
            document_id = _slugify_stem(path.stem)
            try:
                content = path.read_text(encoding="utf-8")
                file_hash = content_hash(normalize(content))
            except Exception:  # noqa: BLE001 — unreadable file: report, continue
                print(f"[knowledge] FAILED   {relative} (file could not be read)")
                failed += 1
                continue

            document = db.get(Document, document_id)

            if document is not None and document.content and document.content_hash == file_hash:
                print(f"[knowledge] current  {relative}")
                unchanged += 1
                continue

            if args.dry_run:
                state = "missing" if document is None else "changed"
                print(f"[knowledge] {state:<8} {relative}")
                continue

            try:
                if document is None:
                    title = document_id.replace("-", " ").title()
                    service.create_document(
                        DocumentCreate(
                            title=title,
                            content=content,
                            source=relative,
                            source_type="markdown",
                            knowledge_status=knowledge_status,
                        ),
                        document_id=document_id,
                    )
                    created += 1
                    print(f"[knowledge] created  {relative}")
                else:
                    service.ingest_content(
                        document,
                        content=content,
                        source_type="markdown",
                        source=relative,
                        knowledge_status=knowledge_status,
                    )
                    updated += 1
                    print(f"[knowledge] updated  {relative}")
            except Exception as exc:  # noqa: BLE001 — one bad file never blocks the rest
                db.rollback()
                failed += 1
                print(f"[knowledge] FAILED   {relative}: {exc}")

    if not args.dry_run:
        print(
            f"[knowledge] done: updated={updated} created={created} "
            f"unchanged={unchanged} failed={failed}"
        )
    return 0


def _knowledge_files_dir() -> Path:
    from app.db.seed import KNOWLEDGE_DIR

    return KNOWLEDGE_DIR.parent


def _slugify_stem(stem: str) -> str:
    from app.ingestion.pipeline import slugify

    return slugify(stem)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
