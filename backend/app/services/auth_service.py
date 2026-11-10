"""Staff authentication: accounts, sign-in, bearer sessions.

Security notes:
- Passwords are hashed with PBKDF2-SHA256 (Python stdlib, deliberately
  no new dependency): 240,000 iterations, a per-user 16-byte random
  salt, and a constant-time comparison. The stored string keeps its
  parameters (`pbkdf2_sha256$iterations$salt$hash`) so the cost can be
  raised later without breaking existing accounts.
- Sessions are opaque bearer tokens from `secrets` (never derivable
  from user data). Only the SHA-256 hash of a token is stored, so a
  database leak cannot produce a usable credential; the raw token is
  returned exactly once at sign-in and lives only in the staff browser.
- Verification is server-side on every request; expired sessions are
  deleted when encountered (never honored) and pruned at sign-in.
- Unknown email and wrong password produce the SAME 401 message —
  the endpoint never reveals which accounts exist.
"""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import ConflictError, UnauthorizedError
from app.models.entities import StaffSession, StaffUser

_HASH_NAME = "pbkdf2_sha256"
_PBKDF2_ITERATIONS = 240_000
_SALT_BYTES = 16
_HASH_BYTES = 32

_SESSION_TOKEN_BYTES = 32  # → 256-bit token


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def hash_password(password: str) -> str:
    salt = secrets.token_hex(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("ascii"), _PBKDF2_ITERATIONS,
        dklen=_HASH_BYTES,
    )
    return f"{_HASH_NAME}${_PBKDF2_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time verification; any malformed stored hash → False."""
    try:
        name, iterations, salt, expected_hex = stored.split("$", 3)
        if name != _HASH_NAME:
            return False
        expected = bytes.fromhex(expected_hex)
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt.encode("ascii"), int(iterations),
            dklen=len(expected),
        )
        return hmac.compare_digest(digest, expected)
    except (ValueError, TypeError):
        return False


class AuthService:
    """Account + session workflows over the StaffUser/StaffSession rows."""

    def __init__(self, db: Session):
        self.db = db

    # --- queries ---------------------------------------------------------

    def has_any_user(self) -> bool:
        """True once at least one staff account exists (first-run gate)."""
        return self.db.scalar(select(StaffUser.id).limit(1)) is not None

    # --- workflows -------------------------------------------------------

    def register(self, *, name: str, email: str, password: str) -> tuple[StaffUser, str, datetime]:
        """Create the staff account and open its first session.

        409 — the email is already registered. Returns (user, token,
        expires_at); the token is returned once and never persisted raw.
        """
        normalized = email.strip().lower()
        existing = self.db.scalar(select(StaffUser).where(StaffUser.email == normalized))
        if existing is not None:
            raise ConflictError("An account with this email already exists.")

        user = StaffUser(name=name.strip(), email=normalized, password_hash=hash_password(password))
        self.db.add(user)
        self.db.commit()
        token, expires_at = self._open_session(user)
        return user, token, expires_at

    def login(self, *, email: str, password: str) -> tuple[StaffUser, str, datetime]:
        """Verify credentials and open a new session.

        401 — unknown email OR wrong password (identical message).
        Expired sessions for the account are pruned opportunistically.
        """
        normalized = email.strip().lower()
        user = self.db.scalar(select(StaffUser).where(StaffUser.email == normalized))
        if user is None or not verify_password(password, user.password_hash):
            raise UnauthorizedError("Email or password is incorrect.")

        user.last_login_at = _utcnow()
        self.db.commit()
        self._prune_expired(user.id)
        token, expires_at = self._open_session(user)
        return user, token, expires_at

    def authenticate(self, token: str | None) -> StaffUser:
        """Resolve a bearer token to its staff user; raise 401 otherwise.

        Runs on EVERY protected request: unknown token, expired session,
        and missing token are all the same safe 401. Expired rows are
        deleted here so they can never be honored twice.
        """
        if not token:
            raise UnauthorizedError("Sign in to the staff workspace to continue.")

        session = self.db.scalar(
            select(StaffSession).where(StaffSession.token_hash == _token_hash(token))
        )
        if session is None:
            raise UnauthorizedError("This session is no longer valid. Please sign in again.")
        if session.expires_at <= _utcnow():
            self.db.delete(session)
            self.db.commit()
            raise UnauthorizedError("Your session has expired. Please sign in again.")
        return session.user

    def logout(self, token: str | None) -> None:
        """Delete the session row. Idempotent: an unknown token is a no-op."""
        if not token:
            return
        self.db.execute(
            delete(StaffSession).where(StaffSession.token_hash == _token_hash(token))
        )
        self.db.commit()

    # --- internals -------------------------------------------------------

    def _open_session(self, user: StaffUser) -> tuple[str, datetime]:
        ttl_days = get_settings().auth_session_ttl_days
        expires_at = _utcnow() + timedelta(days=ttl_days)
        token = secrets.token_urlsafe(_SESSION_TOKEN_BYTES)
        self.db.add(
            StaffSession(
                token_hash=_token_hash(token),
                user_id=user.id,
                expires_at=expires_at,
            )
        )
        self.db.commit()
        return token, expires_at

    def _prune_expired(self, user_id: str) -> None:
        self.db.execute(
            delete(StaffSession).where(
                StaffSession.user_id == user_id,
                StaffSession.expires_at <= _utcnow(),
            )
        )
        self.db.commit()
