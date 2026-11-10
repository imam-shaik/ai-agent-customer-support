"""Staff authentication endpoints (register / login / me / logout)."""

from datetime import datetime

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.api.deps import _bearer_scheme, get_current_staff
from app.db.session import get_db
from app.models.entities import StaffUser
from app.schemas.auth import AuthSessionOut, AuthStatusOut, LoginIn, RegisterIn, StaffUserOut
from app.services.auth_service import AuthService

router = APIRouter(tags=["auth"])


def _session_out(user: StaffUser, token: str, expires_at: datetime) -> AuthSessionOut:
    return AuthSessionOut(
        token=token,
        expires_at=expires_at,
        user=StaffUserOut(
            id=user.id,
            name=user.name,
            email=user.email,
            created_at=user.created_at,
            last_login_at=user.last_login_at,
        ),
    )


@router.get("/auth/status", response_model=AuthStatusOut)
def auth_status(db: Session = Depends(get_db)) -> AuthStatusOut:
    """First-run probe for the staff workspace: which screen to open."""
    return AuthStatusOut(has_staff_user=AuthService(db).has_any_user())


@router.post(
    "/auth/register",
    response_model=AuthSessionOut,
    status_code=status.HTTP_201_CREATED,
)
def register(payload: RegisterIn, db: Session = Depends(get_db)) -> AuthSessionOut:
    """Create the staff account and sign in.

    409 — the email is already registered. The bearer token is returned
    once and never stored in raw form.
    """
    user, token, expires_at = AuthService(db).register(
        name=payload.name, email=payload.email, password=payload.password
    )
    return _session_out(user, token, expires_at)


@router.post("/auth/login", response_model=AuthSessionOut)
def login(payload: LoginIn, db: Session = Depends(get_db)) -> AuthSessionOut:
    """Sign in with email + password.

    401 — unknown email OR wrong password (identical message either way).
    """
    user, token, expires_at = AuthService(db).login(
        email=payload.email, password=payload.password
    )
    return _session_out(user, token, expires_at)


@router.get("/auth/me", response_model=StaffUserOut)
def me(current_staff: StaffUser = Depends(get_current_staff)) -> StaffUser:
    """Who am I signed in as? 401 — missing/unknown/expired token."""
    return current_staff


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    current_staff: StaffUser = Depends(get_current_staff),
    credentials=Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> Response:
    """Invalidate the current session token. Idempotent."""
    AuthService(db).logout(credentials.credentials if credentials else None)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
