# tests/test_streams.py - Limite de telas simultaneas (heartbeat do app)
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.models.stream_session import StreamSession
from app.routes import player as player_routes
from app.services import streams


class FakeResult:
    def __init__(self, value=None) -> None:
        self.value = value

    def scalars(self):
        return self

    def all(self):
        return self.value if isinstance(self.value, list) else []

    def scalar_one_or_none(self):
        return self.value

    def first(self):
        return self.value


class FakeSession:
    """Entrega resultados na ordem em que as consultas chegam."""

    def __init__(self, *results) -> None:
        self.results = list(results)
        self.added = []
        self.commits = 0

    async def execute(self, *args, **kwargs):
        if self.results:
            return FakeResult(self.results.pop(0))
        return FakeResult([])

    def add(self, obj) -> None:
        self.added.append(obj)

    async def commit(self) -> None:
        self.commits += 1


def make_session(**kwargs) -> StreamSession:
    now = datetime.now(UTC)
    data = {
        "id": uuid4(),
        "user_id": uuid4(),
        "subscription_id": uuid4(),
        "device_id": "aparelho-1",
        "channel_ref": "abc123",
        "channel_name": "Canal",
        "started_at": now,
        "last_heartbeat": now,
    }
    data.update(kwargs)
    return StreamSession(**data)


async def test_first_device_opens_a_session():
    db = FakeSession([])

    session = await streams.start_session(
        db,
        user_id=uuid4(),
        subscription_id=uuid4(),
        device_id="aparelho-1",
        channel_ref="abc",
        channel_name="Canal",
        limit=1,
    )

    assert db.added == [session]
    assert session.device_id == "aparelho-1"
    assert db.commits == 1


async def test_second_device_is_blocked_when_limit_is_one():
    """O furo que existia: 1 tela no contrato, ilimitado na pratica."""
    db = FakeSession([make_session(device_id="aparelho-1")])

    with pytest.raises(streams.StreamLimitError) as exc:
        await streams.start_session(
            db,
            user_id=uuid4(),
            subscription_id=uuid4(),
            device_id="aparelho-2",
            channel_ref="def",
            channel_name="Outro canal",
            limit=1,
        )

    assert exc.value.limit == 1
    assert db.added == []


async def test_same_device_reuses_the_session():
    """Trocar de canal no mesmo aparelho nao pode gastar vaga."""
    existing = make_session(device_id="aparelho-1", channel_name="Antigo")
    db = FakeSession([existing])

    session = await streams.start_session(
        db,
        user_id=uuid4(),
        subscription_id=uuid4(),
        device_id="aparelho-1",
        channel_ref="novo",
        channel_name="Novo canal",
        limit=1,
    )

    assert session is existing
    assert session.channel_name == "Novo canal"
    assert db.added == []
    assert db.commits == 1


async def test_plan_with_two_streams_allows_second_device():
    db = FakeSession([make_session(device_id="aparelho-1")])

    session = await streams.start_session(
        db,
        user_id=uuid4(),
        subscription_id=uuid4(),
        device_id="aparelho-2",
        channel_ref="def",
        channel_name="Outro",
        limit=2,
    )

    assert session.device_id == "aparelho-2"


async def test_heartbeat_returns_none_for_closed_session():
    closed = make_session(ended_at=datetime.now(UTC))
    db = FakeSession(closed)

    assert await streams.heartbeat(db, user_id=uuid4(), session_id=uuid4()) is None


async def test_heartbeat_extends_the_session():
    session = make_session(last_heartbeat=datetime.now(UTC) - timedelta(seconds=90))
    past = session.last_heartbeat
    db = FakeSession(session)

    refreshed = await streams.heartbeat(db, user_id=uuid4(), session_id=uuid4())

    assert refreshed is session
    assert session.last_heartbeat > past


async def test_stop_session_ends_it():
    session = make_session()
    db = FakeSession(session)

    assert await streams.stop_session(db, user_id=uuid4(), session_id=uuid4()) is True
    assert session.ended_at is not None


async def test_stop_session_is_idempotent():
    session = make_session(ended_at=datetime.now(UTC))
    db = FakeSession(session)

    assert await streams.stop_session(db, user_id=uuid4(), session_id=uuid4()) is False


async def test_play_route_returns_403_with_stream_limit_code(monkeypatch):
    """O app depende desse codigo para explicar o bloqueio ao assinante."""

    async def boom(*args, **kwargs):
        raise streams.StreamLimitError(1)

    monkeypatch.setattr(player_routes, "start_session", boom)
    subscription = SimpleNamespace(
        id=uuid4(),
        user_id=uuid4(),
        plan=SimpleNamespace(max_simultaneous_streams=1),
    )

    with pytest.raises(HTTPException) as exc:
        await player_routes.start_playback(
            player_routes.StreamPlayRequest(channel_url="http://provedor/canal/1.ts"),
            subscription=subscription,
            device_id="aparelho-1",
            db=FakeSession(),
        )

    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "stream_limit"


async def test_play_route_reports_limit_and_active_count(monkeypatch):
    session = make_session()
    captured = {}

    async def fake_start(db, **kwargs):
        captured.update(kwargs)
        return session

    async def fake_active(db, user_id):
        return [session]

    monkeypatch.setattr(player_routes, "start_session", fake_start)
    monkeypatch.setattr(player_routes, "active_sessions", fake_active)
    subscription = SimpleNamespace(
        id=uuid4(),
        user_id=uuid4(),
        plan=SimpleNamespace(max_simultaneous_streams=1),
    )

    response = await player_routes.start_playback(
        player_routes.StreamPlayRequest(channel_url="http://provedor/canal/1.ts", channel_name="Canal"),
        subscription=subscription,
        device_id="aparelho-1",
        db=FakeSession(),
    )

    assert response.limit == 1
    assert response.active == 1
    # A URL do provedor nao vai para o banco: guarda apenas o hash.
    assert captured["channel_ref"] != "http://provedor/canal/1.ts"
    assert len(captured["channel_ref"]) == 32
    assert captured["channel_name"] == "Canal"


async def test_heartbeat_route_reports_closed_session(monkeypatch):
    async def fake_heartbeat(db, **kwargs):
        return None

    monkeypatch.setattr(player_routes, "heartbeat", fake_heartbeat)
    subscription = SimpleNamespace(id=uuid4(), user_id=uuid4())

    with pytest.raises(HTTPException) as exc:
        await player_routes.stream_heartbeat(
            player_routes.StreamHeartbeatRequest(session_id=uuid4()),
            subscription=subscription,
            db=FakeSession(),
        )

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "session_closed"


def test_stream_limit_is_capped_by_operational_setting(monkeypatch):
    """Plano criado por engano com 10 telas nao pode furar a regra comercial."""
    from app.config import settings

    monkeypatch.setattr(settings, "MAX_STREAMS_PER_SUBSCRIPTION", 2)
    subscription = SimpleNamespace(plan=SimpleNamespace(max_simultaneous_streams=10))

    assert streams.stream_limit(subscription) == 2


def test_stream_limit_respects_the_plan_when_below_the_cap(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "MAX_STREAMS_PER_SUBSCRIPTION", 2)
    subscription = SimpleNamespace(plan=SimpleNamespace(max_simultaneous_streams=1))

    assert streams.stream_limit(subscription) == 1


def test_stream_limit_without_plan_defaults_to_one(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "MAX_STREAMS_PER_SUBSCRIPTION", 2)

    assert streams.stream_limit(SimpleNamespace(plan=None)) == 1
