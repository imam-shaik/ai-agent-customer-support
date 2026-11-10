"""Purge tickets from the development database.

The staff queue must show ONLY tickets actually raised through the
customer escalation flow. End-to-end smoke runs (scripts/smoke.py) and
earlier manual experiments leave real rows behind — this utility deletes
them. It never touches the knowledge corpus or staff accounts.

Usage (from backend/):
    python scripts/clear_tickets.py            # preview counts
    python scripts/clear_tickets.py --yes      # delete ALL tickets
    python scripts/clear_tickets.py --yes --with-conversations
                                               # also drop conversations
                                               # left without tickets
                                               # (smoke-run leftovers)

The database URL comes from the environment / backend/.env exactly like
the server (DATABASE_URL).
"""

import argparse
import sys
from pathlib import Path

# Make `app` importable when run from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import SessionLocal  # noqa: E402
from app.models import Conversation, StaffReply, Ticket, TicketEvent  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Delete tickets from the dev database.")
    parser.add_argument("--yes", action="store_true", help="Actually delete (no dry-run).")
    parser.add_argument(
        "--with-conversations",
        action="store_true",
        help="Also delete conversations that no longer have any ticket.",
    )
    parser.add_argument(
        "--keep-customer",
        action="append",
        metavar="NAME",
        help="Never delete tickets whose customer name matches (repeatable).",
    )
    args = parser.parse_args()

    with SessionLocal() as db:
        tickets = db.query(Ticket).all()
        keep = {name.lower() for name in (args.keep_customer or [])}
        if keep:
            tickets = [t for t in tickets if t.customer_name.lower() not in keep]
        events = db.query(TicketEvent).count()
        replies = db.query(StaffReply).count()

        print(f"Tickets: {len(tickets)} | ticket events: {events} | staff replies: {replies}")
        for ticket in tickets:
            print(f"  - {ticket.id}  {ticket.status:<11} {ticket.customer_name!r} — {ticket.summary}")

        orphan_conversations: list[Conversation] = []
        if args.with_conversations:
            orphan_conversations = [
                conversation
                for conversation in db.query(Conversation).all()
                if not conversation.tickets
            ]
            print(f"Conversations without tickets: {len(orphan_conversations)}")

        if not args.yes:
            print("\nDry run — nothing deleted. Re-run with --yes to delete.")
            return 0

        # Staff replies and ticket events cascade with their ticket
        # (ondelete=CASCADE); delete tickets explicitly for a clear log.
        deleted = len(tickets)
        for ticket in tickets:
            db.delete(ticket)
        if orphan_conversations and not keep:
            # The with-conversations sweep only makes sense for a full wipe;
            # with a keep-filter, live conversations must stay untouched.
            for conversation in orphan_conversations:
                db.delete(conversation)
        db.commit()
        print(f"\nDeleted {deleted} ticket(s)"
              + (f" and {len(orphan_conversations)} orphan conversation(s)." if args.with_conversations and not keep else "."))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
