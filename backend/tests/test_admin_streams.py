# tests/test_admin_streams.py - Painel de quem esta assistindo agora
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from app.config import settings
from app.models.stream_session import StreamSession
from app.routes import admin


class FakeResult:
    def __init__(self, rows) -> None:
        self.rows = rows

    def all(self):
        return self.rows


class FakeSession:
    def __init__(self, rows) -> None:
        self.rows = rows

    async def execute(self, *args, **kwargs):
        return FakeResult(self.rows)


def make_stream(last_heartbeat: datetime) -> StreamSession:
    return StreamSession(
        id=uuid4(),
        user_id=uuid4(),
        subscription_id=uuid4(),
        device_id="aparelho-1",
        channel_ref="abc",
        channel_name="Canal",
        started_at=last_heartbeat,
        last_heartbeat=last_heartbeat,
    )


def make_user() -> SimpleNamespace:
    return SimpleNamespace(id=uuid4(), email="cliente@example.com")


async def test_active_sessions_count_towards_the_limit(monkeypatch):
    monkeypatch.setattr(settings, "STREAM_SESSION_TIMEOUT_SECONDS", 120)
    recent = make_stream(datetime.now(UTC) - timedelta(seconds=10))

    result = await admin.list_stream_sessions(db=FakeSession([(recent, make_user())]), _=None)

    assert result["active_count"] == 1
    assert result["limit_seconds"] == 120
    assert result["sessions"][0]["email"] == "cliente@example.com"
    assert result["sessions"][0]["active"] is True


async def test_stale_sessions_are_listed_but_not_counted(monkeypatch):
    """Sessao sem heartbeat continua no banco, mas nao segura a vaga."""
    monkeypatch.setattr(settings, "STREAM_SESSION_TIMEOUT_SECONDS", 120)
    stale = make_stream(datetime.now(UTC) - timedelta(minutes=30))

    result = await admin.list_stream_sessions(db=FakeSession([(stale, make_user())]), _=None)

    assert result["sessions"][0]["active"] is False
    assert result["active_count"] == 0


async def test_no_sessions_returns_empty_list():
    result = await admin.list_stream_sessions(db=FakeSession([]), _=None)

    assert result["sessions"] == []
    assert result["active_count"] == 0
