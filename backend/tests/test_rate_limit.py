# tests/test_rate_limit.py - Rate limit por identidade, gravado no banco
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException, Request, Response
from fastapi import status as http_status
from sqlalchemy.sql.dml import Delete

from app.routes import auth as auth_routes
from app.schemas.auth import UserLogin
from app.security import dependencies as deps
from app.services import rate_limit


def make_request(ip: str | None = "10.0.0.1", forwarded: str | None = None) -> Request:
    headers = []
    if forwarded:
        headers.append((b"x-forwarded-for", forwarded.encode()))
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/auth/login",
        "headers": headers,
        "client": (ip, 54321) if ip else None,
    }
    return Request(scope)


class FakeResult:
    def __init__(self, value=None) -> None:
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def scalars(self):
        return self

    def all(self):
        return self.value or []


def _key_of(stmt) -> str | None:
    """Extrai a chave do WHERE da consulta/delete usada pelo limiter."""
    try:
        clause = stmt.whereclause
        if clause is None:
            return None
        return str(clause.right.value)
    except Exception:  # noqa: BLE001 - consulta que nao e do limiter
        return None


class FakeDB:
    """Banco minimo: guarda os contadores em um dicionario."""

    def __init__(self, counters: dict | None = None) -> None:
        self.counters = dict(counters or {})
        self.commits = 0
        self.added = []

    async def execute(self, stmt):
        key = _key_of(stmt)
        if key is None:
            return FakeResult(None)
        if isinstance(stmt, Delete):
            self.counters.pop(key, None)
            return FakeResult(None)
        return FakeResult(self.counters.get(key))

    def add(self, obj) -> None:
        self.counters[obj.key] = obj
        self.added.append(obj)

    async def commit(self) -> None:
        self.commits += 1


def make_counter(key: str, count: int = 1, window_start: datetime | None = None):
    counter = rate_limit.RateLimitCounter(
        key=key,
        count=count,
        window_start=window_start or datetime.now(UTC),
    )
    return counter


def test_client_ip_prefers_forwarded_header():
    """Atras do proxy do Render, host e o IP do proxy; o real vem no XFF."""
    request = make_request(ip="10.10.0.5", forwarded="203.0.113.7, 10.10.0.5")

    assert deps.client_ip(request) == "203.0.113.7"


def test_client_ip_falls_back_to_connection_host():
    request = make_request(ip="192.168.1.9", forwarded=None)

    assert deps.client_ip(request) == "192.168.1.9"


async def test_limit_is_per_identity_not_per_ip():
    """Duas contas do mesmo IP nao dividem o mesmo balde."""
    db = FakeDB()

    for _ in range(3):
        await rate_limit.hit(db, key=rate_limit.scoped_key("register", "a@x.com"), limit=3, window_seconds=60)

    with pytest.raises(HTTPException) as exc:
        await rate_limit.hit(
            db, key=rate_limit.scoped_key("register", "a@x.com"), limit=3, window_seconds=60
        )
    assert exc.value.status_code == http_status.HTTP_429_TOO_MANY_REQUESTS

    # Outra conta segue normalmente, mesmo vindo do mesmo "IP".
    await rate_limit.hit(db, key=rate_limit.scoped_key("register", "b@x.com"), limit=3, window_seconds=60)


async def test_window_resets_after_expiry():
    now = datetime.now(UTC)
    key = rate_limit.scoped_key("register", "a@x.com")
    db = FakeDB({key: make_counter(key, count=5, window_start=now - timedelta(hours=2))})

    # Janela de 1h ja passou: volta a contar do zero.
    await rate_limit.hit(db, key=key, limit=1, window_seconds=3600, now=now)

    assert db.counters[key].count == 1


def test_identity_is_case_insensitive_and_trimmed():
    assert rate_limit.scoped_key("register", "  Cliente@Example.com ") == "register:cliente@example.com"


async def test_login_failures_lock_only_that_account(monkeypatch):
    """Blindagem por conta: nao depende de IP (proxy unico do Render)."""
    monkeypatch.setattr(deps.settings, "RATE_LIMIT_LOGIN_FAILURES", 3)
    db = FakeDB()

    for _ in range(3):
        await deps.check_login_failures(db, "victima@example.com")

    with pytest.raises(HTTPException) as exc:
        await deps.check_login_failures(db, "victima@example.com")

    assert exc.value.status_code == http_status.HTTP_429_TOO_MANY_REQUESTS

    # Outra conta segue entrando normalmente.
    await deps.check_login_failures(db, "outra@example.com")


async def test_successful_login_resets_the_counter(monkeypatch):
    monkeypatch.setattr(deps.settings, "RATE_LIMIT_LOGIN_FAILURES", 3)
    db = FakeDB()

    for _ in range(3):
        await deps.check_login_failures(db, "cliente@example.com")
    await deps.record_login_success(db, "cliente@example.com")

    # Contador zerado: nova tentativa volta a ser aceita.
    await deps.check_login_failures(db, "cliente@example.com")
    await deps.check_login_failures(db, "cliente@example.com")


async def test_login_key_is_case_insensitive(monkeypatch):
    monkeypatch.setattr(deps.settings, "RATE_LIMIT_LOGIN_FAILURES", 1)
    db = FakeDB()

    await deps.check_login_failures(db, "Cliente@Example.com")

    with pytest.raises(HTTPException):
        # Mesma conta escrita de outro jeito nao escapa do bloqueio.
        await deps.check_login_failures(db, "cliente@example.com")


async def test_login_route_blocks_after_failed_attempts(monkeypatch):
    """De ponta a ponta: chutar senha repetidas vezes acaba em 429."""
    monkeypatch.setattr(deps.settings, "RATE_LIMIT_LOGIN_FAILURES", 3)
    db = FakeDB()
    data = UserLogin(email="cliente@example.com", password="senha-errada")

    for _ in range(3):
        with pytest.raises(HTTPException) as attempt:
            await auth_routes.login(data, Response(), db=db, x_device_id=None)
        assert attempt.value.status_code == http_status.HTTP_401_UNAUTHORIZED

    with pytest.raises(HTTPException) as blocked:
        await auth_routes.login(data, Response(), db=db, x_device_id=None)
    assert blocked.value.status_code == http_status.HTTP_429_TOO_MANY_REQUESTS
