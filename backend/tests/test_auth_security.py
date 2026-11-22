# tests/test_auth_security.py - Endurecimento de autenticacao e admin
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException, Response

from app.routes import admin as admin_routes
from app.routes import auth as auth_routes
from app.schemas.auth import UserRegister, UserUpdate
from app.services.auth_service import hash_password, verify_password


class FakeResult:
    def __init__(self, value=None) -> None:
        self.value = value

    def scalar_one(self):
        return self.value

    def scalar_one_or_none(self):
        return self.value

    def scalars(self):
        return self

    def all(self):
        return self.value or []


class FakeSession:
    """Entrega resultados na ordem em que as consultas chegam."""

    def __init__(self, *results) -> None:
        self.results = list(results)
        self.added = []
        self.commits = 0
        self.refreshed = []

    async def execute(self, *args, **kwargs):
        return FakeResult(self.results.pop(0) if self.results else None)

    def add(self, obj) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                obj.id = uuid4()

    async def commit(self) -> None:
        self.commits += 1

    async def refresh(self, obj) -> None:
        self.refreshed.append(obj)

    async def rollback(self) -> None:
        return None


async def _noop(*args, **kwargs) -> None:
    return None


def make_user(**kwargs):
    data = {
        "id": uuid4(),
        "email": "cliente@example.com",
        "full_name": "Cliente",
        "phone": None,
        "email_verified": True,
        "is_active": True,
        "is_admin": False,
        "password_hash": "hash-antigo",
    }
    data.update(kwargs)
    return SimpleNamespace(**data)


async def test_reset_password_revokes_sessions_and_does_not_reactivate(monkeypatch):
    user = make_user(
        is_active=False,
        password_reset_token="hash",
        is_password_reset_code_valid=lambda code: code == "123456",
    )
    db = FakeSession(user)
    revoked = {}

    async def fake_revoke_all(session, user_id, **kwargs):
        revoked["user_id"] = user_id
        revoked["commit"] = kwargs.get("commit")
        return 2

    monkeypatch.setattr(auth_routes.rate_limit, "hit", _noop)
    monkeypatch.setattr(auth_routes.sessions, "revoke_all", fake_revoke_all)

    data = SimpleNamespace(
        email="cliente@example.com", code="123456", new_password="senha-nova-123"
    )
    response = await auth_routes.reset_password(data, request=None, db=db)

    assert "Senha alterada" in response.message
    assert revoked["user_id"] == user.id
    assert revoked["commit"] is False
    assert user.is_active is False
    assert user.password_reset_token is None
    assert verify_password("senha-nova-123", user.password_hash)


async def test_update_me_requires_the_current_password(monkeypatch):
    user = make_user(password_hash=hash_password("senha-atual-123"))
    db = FakeSession()
    revoked = []

    async def fake_revoke_all(session, user_id, **kwargs):
        revoked.append(user_id)

    monkeypatch.setattr(auth_routes.sessions, "revoke_all", fake_revoke_all)

    with pytest.raises(HTTPException) as exc:
        await auth_routes.update_me(UserUpdate(password="senha-nova-123"), user=user, db=db)
    assert exc.value.status_code == 400

    with pytest.raises(HTTPException) as exc:
        await auth_routes.update_me(
            UserUpdate(password="senha-nova-123", current_password="errada"),
            user=user,
            db=db,
        )
    assert exc.value.status_code == 400
    assert revoked == []
    assert db.commits == 0

    await auth_routes.update_me(
        UserUpdate(password="senha-nova-123", current_password="senha-atual-123"),
        user=user,
        db=db,
    )

    assert revoked == [user.id]
    assert verify_password("senha-nova-123", user.password_hash)
    assert db.commits == 1


async def test_delete_me_blocks_the_last_admin():
    user = make_user(is_admin=True)
    db = FakeSession(1)

    with pytest.raises(HTTPException) as exc:
        await auth_routes.delete_me(user=user, db=db)

    assert exc.value.status_code == 400
    assert "ultimo administrador" in exc.value.detail


async def test_login_checks_a_dummy_hash_when_email_does_not_exist(monkeypatch):
    db = FakeSession(None)
    seen = []

    monkeypatch.setattr(auth_routes, "check_login_failures", _noop)
    monkeypatch.setattr(auth_routes, "dummy_password_hash", lambda: "dummy")
    monkeypatch.setattr(
        auth_routes, "verify_password", lambda password, hashed: seen.append((password, hashed))
    )

    data = SimpleNamespace(email="fantasma@example.com", password="segredo-123")
    with pytest.raises(HTTPException) as exc:
        await auth_routes.login(data, Response(), db=db)

    assert exc.value.status_code == 401
    assert seen == [("segredo-123", "dummy")]


async def test_claim_ownership_rejects_when_an_admin_exists():
    user = make_user()
    db = FakeSession(1)

    with pytest.raises(HTTPException) as exc:
        await admin_routes.claim_ownership(db=db, current_user=user)

    assert exc.value.status_code == 403


async def test_claim_ownership_requires_verified_email():
    user = make_user(email_verified=False)
    db = FakeSession(0)

    with pytest.raises(HTTPException) as exc:
        await admin_routes.claim_ownership(db=db, current_user=user)

    assert exc.value.status_code == 403
    assert "email" in exc.value.detail.lower()


async def test_claim_ownership_only_allows_the_oldest_account():
    user = make_user()
    db = FakeSession(0, uuid4())

    with pytest.raises(HTTPException) as exc:
        await admin_routes.claim_ownership(db=db, current_user=user)

    assert exc.value.status_code == 403


async def test_register_marks_the_first_account_as_admin(monkeypatch):
    db = FakeSession(None, 0)

    monkeypatch.setattr(auth_routes.rate_limit, "hit", _noop)
    monkeypatch.setattr(auth_routes.email_service, "send_verification_email", _noop)

    data = UserRegister(email="dono@example.com", password="senha-forte-123")
    await auth_routes.register(data, request=None, response=Response(), db=db)

    created = db.added[0]
    assert created.email == "dono@example.com"
    assert created.is_admin is True


async def test_register_does_not_create_a_new_admin_when_users_exist(monkeypatch):
    db = FakeSession(None, 5)

    monkeypatch.setattr(auth_routes.rate_limit, "hit", _noop)
    monkeypatch.setattr(auth_routes.email_service, "send_verification_email", _noop)

    data = UserRegister(email="cliente@example.com", password="senha-forte-123")
    await auth_routes.register(data, request=None, response=Response(), db=db)

    created = db.added[0]
    assert created.is_admin is False


def test_long_password_is_not_truncated_at_72_bytes():
    """bcrypt puro ignorava o restante; bcrypt_sha256 cobre a senha inteira."""
    long_password = "a" * 80
    hashed = hash_password(long_password)

    assert verify_password(long_password, hashed) is True
    assert verify_password("a" * 72, hashed) is False
