"""Knowledge seed: ingests backend/knowledge/*.md through the REAL pipeline.

There is deliberately no direct-DB document creation here — every seeded
document is validated, normalized, section-detected and chunked by the
same code path as an API upload, so the seed doubles as a pipeline
smoke test on every startup.

Layout:
    knowledge/approved/*.md   — approved Northstar Desk help articles
    knowledge/challenge/*.md  — clearly-labeled challenge fixtures
                                (deliberate conflicting evidence)

Document ids are the file-name slug (getting-started, billing, …) so the
stable citation ids used by the frontend and by Phase 5 citations keep
working. The seed is idempotent: files whose document already has stored
content are skipped; legacy Phase 5 rows (content NULL) are healed by
ingesting the file into the existing row.

A failing file is logged and skipped — knowledge problems never stop the
server from starting.

Run manually:  python -m app.db.seed
Auto-run:      at app startup when ENVIRONMENT != production.
"""

from pathlib import Path

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError
from app.core.logging import get_logger
from app.ingestion.pipeline import extract_title, normalize, slugify
from app.models import Document
from app.schemas.document import DocumentCreate
from app.services.document_service import DocumentService

logger = get_logger("app.seed")

KNOWLEDGE_DIR = Path(__file__).resolve().parents[2] / "knowledge"


def _knowledge_files() -> list[tuple[Path, str]]:
    """Approved documents first, then clearly-labeled challenge fixtures.

    Each file is paired with its knowledge classification: only "approved"
    documents enter normal retrieval (Phase 7+); "challenge_fixture" is the
    labeled conflicting-evidence material.
    """
    files: list[tuple[Path, str]] = []
    for folder, knowledge_status in (("approved", "approved"), ("challenge", "challenge_fixture")):
        directory = KNOWLEDGE_DIR / folder
        if directory.is_dir():
            files.extend((path, knowledge_status) for path in sorted(directory.glob("*.md")))
    return files


def seed_knowledge(db: Session) -> int:
    """Ingest every knowledge file that is not yet processed. Returns count ingested."""
    service = DocumentService(db)
    ingested = 0

    for path, knowledge_status in _knowledge_files():
        relative = path.relative_to(KNOWLEDGE_DIR.parent).as_posix()
        try:
            content = path.read_text(encoding="utf-8")
            document_id = slugify(path.stem)
            title = extract_title(normalize(content), path.stem.replace("-", " ").title())

            existing = db.get(Document, document_id)
            if existing is not None and existing.content:
                if existing.knowledge_status != knowledge_status:
                    # Heal classification on rows ingested before the field
                    # existed (e.g. the challenge fixture on old dev DBs).
                    existing.knowledge_status = knowledge_status
                    db.commit()
                    logger.info(
                        "seed_classification_healed document_id=%s knowledge_status=%s",
                        document_id,
                        knowledge_status,
                    )
                continue  # already ingested — idempotent

            if existing is None:
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
            else:
                # Legacy row from Phase 5 (no stored content): heal it.
                service.ingest_content(
                    existing,
                    content=content,
                    source_type="markdown",
                    source=relative,
                    knowledge_status=knowledge_status,
                )
            ingested += 1
            logger.info("seed_document_ingested document_id=%s source=%s", document_id, relative)
        except ConflictError as exc:
            logger.warning(
                "seed_document_skipped source=%s reason=%s", relative, exc.message
            )
        except Exception:  # noqa: BLE001 — a bad file must not block startup
            logger.exception("seed_document_failed source=%s", relative)

    if ingested:
        logger.info("knowledge_seed_complete ingested=%d", ingested)
    return ingested


if __name__ == "__main__":  # python -m app.db.seed
    from app.db.session import SessionLocal

    with SessionLocal() as session:
        count = seed_knowledge(session)
        print(f"Ingested {count} knowledge document(s).")
