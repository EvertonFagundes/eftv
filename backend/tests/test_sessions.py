# tests/test_sessions.py - Refresh token revogavel (logout e rotacao)
from datetime import UTC, datetime, timedelta

from app.models.refresh_token import RefreshToken
from app.services import sessions


class FakeResult:
    def __init__(self, value=None, rowcount: int = 0) -> None:
        self.value = value
        self.rowcount = rowcount

    def scalar_one_or_none(self):
        return self.value


class FakeSession:
    def __init__(self, token=None, rowcount: int = 0) -> None:
        self.token = token
        self.rowcount = rowcount
        self.added = []
        self.commits = 0

    async def execute(self, *args, **kwargs):
        return FakeResult(self.token, rowcount=self.rowcount)

    def add(self, obj) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        self.commits += 1


def make_token(**kwargs) -> RefreshToken:
    now = datetime.now(UTC)
    data = {
        "jti": "jti-1",
        "user_id": "user-1",
        "expires_at": now + timedelta(days=30),
        "revoked_at": None,
    }
    data.update(kwargs)
    return RefreshToken(**data)


async def test_register_stores_the_issued_token():
    db = FakeSession()
    expires = datetime.now(UTC) + timedelta(days=30)

    token = await sessions.register(
        db,
        user_id="user-1",
        jti="jti-1",
        expires_at=expires,
        device_id="aparelho-1",
    )

    assert token in db.added
    assert token.device_id == "aparelho-1"
    assert db.commits == 1


async def test_register_can_share_the_route_transaction():
    db = FakeSession()

    await sessions.register(
        db,
        user_id="user-1",
        jti="jti-1",
        expires_at=datetime.now(UTC) + timedelta(days=30),
        commit=False,
    )

    assert db.added
    assert db.commits == 0


def test_unknown_token_is_not_usable():
    assert sessions.is_usable(None) is False


def test_revoked_token_is_not_usable():
    assert sessions.is_usable(make_token(revoked_at=datetime.now(UTC))) is False


def test_expired_token_is_not_usable():
    assert sessions.is_usable(
        make_token(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    ) is False


def test_valid_token_is_usable():
    assert sessions.is_usable(make_token()) is True


def test_naive_expiry_is_compared_in_utc():
    """SQLite/dev pode devolver datetime sem tzinfo; nao pode explodir."""
    naive = (datetime.now(UTC) + timedelta(days=1)).replace(tzinfo=None)

    assert sessions.is_usable(make_token(expires_at=naive)) is True


async def test_revoke_marks_the_token():
    token = make_token()
    db = FakeSession(token=token)

    assert await sessions.revoke(db, "jti-1") is True
    assert token.revoked_at is not None
    assert db.commits == 1


async def test_revoke_unknown_token_returns_false():
    db = FakeSession(token=None)

    assert await sessions.revoke(db, "jti-inexistente") is False
    assert db.commits == 0


async def test_revoke_all_drops_every_session_of_the_account():
    db = FakeSession(rowcount=3)

    closed = await sessions.revoke_all(db, "user-1")

    assert closed == 3
    assert db.commits == 1
