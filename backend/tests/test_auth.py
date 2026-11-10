"""Staff authentication: register, login, sessions, protected endpoints.

The suite-wide `staff_auth_bypass` override (conftest) is removed inside
these tests via the `real_auth` fixture, so every request here exercises
the real bearer-token dependency end to end.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.api.deps import get_current_staff
from app.main import app


@pytest.fixture()
def real_auth():
    """Remove the suite-wide auth bypass for this test only."""
    app.dependency_overrides.pop(get_current_staff, None)
    yield


def _unique_email() -> str:
    return f"staff-{uuid.uuid4().hex[:10]}@example.com"


def _register(client, **overrides) -> dict:
    payload = {
        "name": "Maya Chen",
        "email": _unique_email(),
        "password": "123456789",
        **overrides,
    }
    response = client.post("/api/v1/auth/register", json=payload)
    return response


def test_register_returns_session_and_token_works(client, real_auth):
    response = _register(client)
    assert response.status_code == 201
    body = response.json()
    assert body["user"]["name"] == "Maya Chen"
    assert body["user"]["email"] == body["user"]["email"].lower()
    assert len(body["token"]) >= 32
    assert "password" not in body["user"]
    assert "password_hash" not in body["user"]

    me = client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {body['token']}"}
    )
    assert me.status_code == 200
    assert me.json()["email"] == body["user"]["email"]


def test_first_run_status_flips_after_registration(client, db_session, real_auth):
    from app.models.entities import StaffUser

    db_session.query(StaffUser).delete()
    db_session.commit()

    before = client.get("/api/v1/auth/status")
    assert before.status_code == 200
    assert before.json()["hasStaffUser"] is False

    assert _register(client).status_code == 201
    after = client.get("/api/v1/auth/status")
    assert after.json()["hasStaffUser"] is True


def test_duplicate_email_rejected_with_409(client, real_auth):
    payload = {
        "name": "Maya Chen",
        "email": f"dupe-{uuid.uuid4().hex[:8]}@example.com",
        "password": "123456789",
    }
    assert client.post("/api/v1/auth/register", json=payload).status_code == 201

    duplicate = client.post(
        "/api/v1/auth/register",
        json={**payload, "name": "Other Name", "password": "different-pass-1"},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "CONFLICT"


def test_weak_password_rejected(client, real_auth):
    response = _register(client, password="short")
    assert response.status_code == 422


def test_login_success_and_wrong_password(client, real_auth):
    email = _unique_email()
    assert _register(client, email=email).status_code == 201

    good = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "123456789"}
    )
    assert good.status_code == 200
    assert len(good.json()["token"]) >= 32

    wrong = client.post(
        "/api/v1/auth/login", json={"email": email, "password": "wrong-password"}
    )
    assert wrong.status_code == 401
    assert wrong.json()["error"]["code"] == "UNAUTHORIZED"
    assert wrong.json()["error"]["message"] == "Email or password is incorrect."


def test_login_unknown_email_is_same_401_as_wrong_password(client, real_auth):
    unknown = client.post(
        "/api/v1/auth/login",
        json={"email": f"nobody-{uuid.uuid4().hex[:8]}@example.com", "password": "123456789"},
    )
    wrong = client.post(
        "/api/v1/auth/login", json={"email": "also-nobody@example.com", "password": "x"}
    )
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["error"]["message"] == wrong.json()["error"]["message"]


def test_admin_escalations_require_sign_in(client, real_auth):
    denied = client.get("/api/v1/admin/escalations")
    assert denied.status_code == 401
    assert denied.json()["error"]["code"] == "UNAUTHORIZED"

    session = _register(client).json()
    allowed = client.get(
        "/api/v1/admin/escalations", headers={"Authorization": f"Bearer {session['token']}"}
    )
    assert allowed.status_code == 200
    assert "items" in allowed.json()


def test_me_without_token_is_401(client, real_auth):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_logout_invalidates_the_token(client, real_auth):
    session = _register(client).json()
    headers = {"Authorization": f"Bearer {session['token']}"}

    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 204
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401


def test_expired_session_is_deleted_and_rejected(client, db_session, real_auth):
    from app.models.entities import StaffSession, StaffUser

    session = _register(client).json()
    user = db_session.query(StaffUser).filter_by(email=session["user"]["email"]).one()
    row = (
        db_session.query(StaffSession)
        .filter_by(user_id=user.id)
        .order_by(StaffSession.created_at.desc())
        .first()
    )
    row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.commit()

    headers = {"Authorization": f"Bearer {session['token']}"}
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
    # The expired row must be gone, not merely ignored.
    remaining = (
        db_session.query(StaffSession).filter_by(id=row.id).one_or_none()
    )
    assert remaining is None
