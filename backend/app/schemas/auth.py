"""Staff authentication contracts."""

from datetime import datetime

from pydantic import EmailStr, Field

from app.schemas.common import ApiModel


class RegisterIn(ApiModel):
    """Create-account payload. Minimum password length is a product
    decision enforced here (and mirrored client-side)."""

    name: str = Field(min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginIn(ApiModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class StaffUserOut(ApiModel):
    """Never includes the password hash."""

    id: str
    name: str
    email: EmailStr
    created_at: datetime
    last_login_at: datetime | None = None


class AuthSessionOut(ApiModel):
    """Sign-in/register response: the bearer token (shown once) + user."""

    token: str
    expires_at: datetime
    user: StaffUserOut


class AuthStatusOut(ApiModel):
    """First-run probe: has_staff_user=False → the workspace opens on the
    create-account screen; True → the sign-in screen."""

    has_staff_user: bool
