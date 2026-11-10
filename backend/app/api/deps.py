"""Shared FastAPI dependencies."""

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.entities import StaffUser
from app.services.auth_service import AuthService

# auto_error=False so a MISSING header reaches our handler and returns
# the standard 401 error envelope (HTTPBearer's default would be a
# plain 403 without one).
_bearer_scheme = HTTPBearer(auto_error=False, description="Staff session token.")


def get_current_staff(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> StaffUser:
    """Resolve `Authorization: Bearer <token>` to the signed-in staff user.

    401 (UNAUTHORIZED envelope) — missing/unknown/expired token. Used to
    guard every /admin escalation endpoint.
    """
    return AuthService(db).authenticate(credentials.credentials if credentials else None)
