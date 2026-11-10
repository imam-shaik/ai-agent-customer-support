#!/usr/bin/env python
"""Reproducible local PostgreSQL + pgvector dev database (Phase 7).

Phase 7 replaces the SQLite scaffolding with PostgreSQL + pgvector because
semantic search needs the native `vector` type. This machine has no Docker
and no WSL, so the PostgreSQL 16.2 + pgvector binaries ship inside the
Python environment via the `pgserver` package — a reviewer needs nothing
but `pip install -r requirements.txt` to bring the database up.

This script manages ONE dedicated development cluster on a FIXED port so
`DATABASE_URL` stays stable across restarts (pgserver's own get_server()
would pick an ephemeral port on every cold start, which is great for
tests but not for a static .env). Tests do NOT use this cluster: the test
suite starts its own isolated server (see tests/conftest.py).

Usage (from backend/):
    python scripts/dev_db.py start    # initdb on first run, start, create DB
    python scripts/dev_db.py status   # exit 0 when running, 1 otherwise
    python scripts/dev_db.py stop
    python scripts/dev_db.py uri      # print the SQLAlchemy URL

Environment overrides: VILASAT_PG_PORT (default 54329),
VILASAT_PG_DATABASE (default vilasat).
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import pgserver  # PostgreSQL 16.2 + pgvector binaries bundled in the wheel

# pgserver logs its (expected, caught) "no server running" probe at ERROR —
# keep the dev script output clean; real failures still raise.
logging.getLogger("pgserver").setLevel(logging.CRITICAL)

BACKEND_DIR = Path(__file__).resolve().parents[1]
PGDATA = BACKEND_DIR / "data" / "pg"
PORT = int(os.environ.get("VILASAT_PG_PORT", "54329"))
DATABASE = os.environ.get("VILASAT_PG_DATABASE", "vilasat")
PG_USER = "postgres"
SERVER_LOG = PGDATA / "server.log"


def _sql_url() -> str:
    return f"postgresql+psycopg://{PG_USER}@127.0.0.1:{PORT}/{DATABASE}"


def _is_running() -> bool:
    if not (PGDATA / "PG_VERSION").exists():
        return False
    try:
        pgserver.pg_ctl(["status"], pgdata=PGDATA)
        return True
    except Exception:  # noqa: BLE001 — pg_ctl exits non-zero when stopped
        return False


def _ensure_initialized() -> None:
    if (PGDATA / "PG_VERSION").exists():
        return
    print(f"[dev-db] initializing cluster at {PGDATA} (first run only)...")
    PGDATA.mkdir(parents=True, exist_ok=True)
    pgserver.initdb(
        [
            f"--auth=trust",  # local development only; never for production
            "--auth-local=trust",
            "--encoding=utf8",
            "-U",
            PG_USER,
        ],
        pgdata=PGDATA,
    )


def _ensure_database() -> None:
    """Create the application database if it does not exist yet."""
    exists = pgserver.psql(
        [
            "-h",
            "127.0.0.1",
            "-p",
            str(PORT),
            "-U",
            PG_USER,
            "-d",
            "postgres",
            "-tAc",
            "SELECT 1 FROM pg_database WHERE datname = '%s'" % DATABASE,
        ]
    ).strip()
    if exists != "1":
        print(f"[dev-db] creating database {DATABASE!r}...")
        pgserver.psql(
            [
                "-h",
                "127.0.0.1",
                "-p",
                str(PORT),
                "-U",
                PG_USER,
                "-d",
                "postgres",
                "-c",
                f'CREATE DATABASE "{DATABASE}"',
            ]
        )


def start() -> None:
    _ensure_initialized()
    if _is_running():
        print(f"[dev-db] already running on 127.0.0.1:{PORT}")
    else:
        print(f"[dev-db] starting PostgreSQL + pgvector on 127.0.0.1:{PORT}...")
        pgserver.pg_ctl(
            [
                "start",
                "-w",  # wait until accepting connections
                "-o",
                f"-p {PORT} -h 127.0.0.1",
                "-l",
                str(SERVER_LOG),
            ],
            pgdata=PGDATA,
        )
    _ensure_database()
    print(f"[dev-db] ready — SQLAlchemy URL: {_sql_url()}")
    print("[dev-db] next: alembic upgrade head   (from backend/)")
    print("[dev-db] next: python scripts/index_knowledge.py   (after seeding)")


def stop() -> None:
    if not _is_running():
        print("[dev-db] not running")
        return
    print("[dev-db] stopping...")
    pgserver.pg_ctl(["stop", "-w", "-m", "fast"], pgdata=PGDATA)
    print("[dev-db] stopped")


def status() -> int:
    running = _is_running()
    state = "running" if running else "stopped"
    print(f"[dev-db] {state} — port={PORT} database={DATABASE} pgdata={PGDATA}")
    print(f"[dev-db] URL: {_sql_url()}")
    if running:
        print(f"[dev-db] server log: {SERVER_LOG}")
        return 0
    print("[dev-db] start it with: python scripts/dev_db.py start")
    return 1


def main(argv: list[str]) -> int:
    command = argv[0] if argv else "status"
    if command == "start":
        start()
        return 0
    if command == "stop":
        stop()
        return 0
    if command == "status":
        return status()
    if command == "uri":
        print(_sql_url())
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
