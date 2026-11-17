# tests/test_device_login.py - Login na TV por codigo (confirmado no celular)
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.config import settings
from app.models.device_login_code import DeviceLoginCode
from app.routes import auth as auth_routes
from app.services import device_login


class FakeResult:
    def __init__(self, value=None) -> None:
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def first(self):
        return self.value


class FakeSession:
    def __init__(self, *results) -> None:
        self.results = list(results)
        self.added = []
        self.commits = 0

    async def execute(self, *args, **kwargs):
        return FakeResult(self.results.pop(0) if self.results else None)

    def add(self, obj) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        self.commits += 1


def make_code(status: str = "pending", minutes: int = 5) -> DeviceLoginCode:
    now = datetime.now(UTC)
    return DeviceLoginCode(
        id=uuid4(),
        code="ABCDEFGH",
        status=status,
        created_at=now,
        expires_at=now + timedelta(minutes=minutes),
    )


def test_code_is_readable_and_unambiguous():
    """Sem 0/O e 1/I: o cliente le na TV e digita no celular."""
    code = device_login._generate_code()

    assert len(code) == device_login.CODE_LENGTH
    assert not set(code) & set("O0I1")
    assert set(code) <= set(device_login.ALPHABET)


def test_format_and_normalize_accept_how_people_type():
    assert device_login.format_code("ABCDEFGH") == "ABCD-EFGH"
    assert device_login.normalize_code("abcd-efgh") == "ABCDEFGH"
    assert device_login.normalize_code(" ABCD EFGH ") == "ABCDEFGH"
    assert device_login.normalize_code(None) == ""


async def test_create_code_stores_expiry_from_settings(monkeypatch):
    monkeypatch.setattr(settings, "DEVICE_CODE_TTL_MINUTES", 10)
    db = FakeSession(None)

    entry = await device_login.create_code(db, "TV da sala")

    assert entry.status == "pending"
    assert entry.device_name == "TV da sala"
    assert (entry.expires_at - entry.created_at) == timedelta(minutes=10)
    assert db.added == [entry]


async def test_approve_generates_tokens_for_the_tv():
    entry = make_code()
    db = FakeSession(entry)

    approved = await device_login.approve_code(
        db, code="abcd-efgh", user_id=uuid4(), email="cliente@example.com"
    )

    assert approved.status == "approved"
    assert approved.access_token
    assert approved.refresh_token
    assert approved.approved_at is not None
    # A TV exibe a conta autorizada: o e-mail viaja junto com os tokens.
    assert approved.email == "cliente@example.com"


async def test_approve_rejects_expired_code():
    db = FakeSession(make_code(minutes=-1))

    with pytest.raises(ValueError) as exc:
        await device_login.approve_code(db, code="ABCD-EFGH", user_id=uuid4())

    assert str(exc.value) == "expired"


async def test_approve_rejects_unknown_code():
    with pytest.raises(ValueError) as exc:
        await device_login.approve_code(FakeSession(None), code="ZZZZZZZZ", user_id=uuid4())

    assert str(exc.value) == "invalid"


async def test_poll_delivers_tokens_only_once():
    """Codigo vazado depois de usado nao pode virar sessao."""
    entry = make_code(status="approved")
    entry.access_token = "access"
    entry.refresh_token = "refresh"
    db = FakeSession(entry)

    state, delivered = await device_login.poll_code(db, "ABCD-EFGH")

    assert state == "approved"
    assert delivered is entry
    assert entry.status == "consumed"


async def test_poll_keeps_waiting_while_pending():
    db = FakeSession(make_code(status="pending"))

    state, delivered = await device_login.poll_code(db, "ABCD-EFGH")

    assert state == "pending"
    assert delivered is None


async def test_poll_expires_stale_code():
    entry = make_code(status="pending", minutes=-1)
    db = FakeSession(entry)

    state, _ = await device_login.poll_code(db, "ABCD-EFGH")

    assert state == "expired"
    assert entry.status == "expired"


async def test_poll_rejects_wrong_length():
    state, _ = await device_login.poll_code(FakeSession(), "ABC")

    assert state == "invalid"


async def test_approve_route_explains_invalid_code(monkeypatch):
    async def boom(*args, **kwargs):
        raise ValueError("invalid")

    monkeypatch.setattr(auth_routes.device_login, "approve_code", boom)

    with pytest.raises(HTTPException) as exc:
        await auth_routes.approve_device_code(
            auth_routes.DeviceCodeApproveRequest(code="ZZZZZZZZ"),
            user=type("U", (), {"id": uuid4(), "email": "cliente@example.com"})(),
            db=FakeSession(),
        )

    assert exc.value.status_code == 404


async def test_approve_route_explains_expired_code(monkeypatch):
    async def boom(*args, **kwargs):
        raise ValueError("expired")

    monkeypatch.setattr(auth_routes.device_login, "approve_code", boom)

    with pytest.raises(HTTPException) as exc:
        await auth_routes.approve_device_code(
            auth_routes.DeviceCodeApproveRequest(code="ABCDEFGH"),
            user=type("U", (), {"id": uuid4(), "email": "cliente@example.com"})(),
            db=FakeSession(),
        )

    assert exc.value.status_code == 410
