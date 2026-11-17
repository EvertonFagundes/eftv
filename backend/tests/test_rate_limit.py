# tests/test_rate_limit.py - Rate limit atras do proxy do Render
import pytest
from fastapi import HTTPException, Request, Response
from fastapi import status as http_status

from app.routes import auth as auth_routes
from app.schemas.auth import UserLogin
from app.security import dependencies as deps


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
        return self.value


class FakeSession:
    """Sem usuario na base: toda tentativa de login falha."""

    async def execute(self, *args, **kwargs):
        return FakeResult(None)


def test_client_ip_prefers_forwarded_header():
    """Atras do proxy do Render, host e o IP do proxy; o real vem no XFF."""
    request = make_request(ip="10.10.0.5", forwarded="203.0.113.7, 10.10.0.5")

    assert deps.client_ip(request) == "203.0.113.7"


def test_client_ip_falls_back_to_connection_host():
    request = make_request(ip="192.168.1.9", forwarded=None)

    assert deps.client_ip(request) == "192.168.1.9"


async def test_general_limit_is_per_ip(monkeypatch):
    monkeypatch.setattr(
        deps, "rate_limiter", deps.RateLimiter(max_requests=1, window_seconds=60)
    )
    first = make_request(forwarded="203.0.113.7")
    other = make_request(forwarded="198.51.100.20")

    await deps.rate_limit_dependency(first)
    with pytest.raises(HTTPException):
        await deps.rate_limit_dependency(first)

    await deps.rate_limit_dependency(other)


def test_login_failures_lock_only_that_account(monkeypatch):
    """Blindagem por conta: nao depende de IP (proxy unico do Render)."""
    monkeypatch.setattr(
        deps, "login_failure_limiter", deps.RateLimiter(max_requests=3, window_seconds=60)
    )

    for _ in range(3):
        deps.check_login_failures("victima@example.com")

    with pytest.raises(HTTPException) as exc:
        deps.check_login_failures("victima@example.com")

    assert exc.value.status_code == http_status.HTTP_429_TOO_MANY_REQUESTS

    # Outra conta segue entrando normalmente.
    deps.check_login_failures("outra@example.com")


def test_successful_login_resets_the_counter(monkeypatch):
    monkeypatch.setattr(
        deps, "login_failure_limiter", deps.RateLimiter(max_requests=3, window_seconds=60)
    )

    for _ in range(3):
        deps.check_login_failures("cliente@example.com")
    deps.record_login_success("cliente@example.com")

    # Contador zerado: nova tentativa volta a ser aceita.
    deps.check_login_failures("cliente@example.com")
    deps.check_login_failures("cliente@example.com")


def test_login_key_is_case_insensitive(monkeypatch):
    monkeypatch.setattr(
        deps, "login_failure_limiter", deps.RateLimiter(max_requests=1, window_seconds=60)
    )

    deps.check_login_failures("Cliente@Example.com")

    with pytest.raises(HTTPException):
        # Mesma conta escrita de outro jeito nao escapa do bloqueio.
        deps.check_login_failures("cliente@example.com")


async def test_login_route_blocks_after_failed_attempts(monkeypatch):
    """De ponta a ponta: chutar senha repetidas vezes acaba em 429."""
    monkeypatch.setattr(
        deps, "login_failure_limiter", deps.RateLimiter(max_requests=3, window_seconds=60)
    )
    session = FakeSession()
    data = UserLogin(email="cliente@example.com", password="senha-errada")

    for _ in range(3):
        with pytest.raises(HTTPException) as attempt:
            await auth_routes.login(data, Response(), db=session)
        assert attempt.value.status_code == http_status.HTTP_401_UNAUTHORIZED

    with pytest.raises(HTTPException) as blocked:
        await auth_routes.login(data, Response(), db=session)
    assert blocked.value.status_code == http_status.HTTP_429_TOO_MANY_REQUESTS
