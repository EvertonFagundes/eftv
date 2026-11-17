# tests/test_rate_limit.py - Rate limit por cliente real, inclusive no login
import pytest
from fastapi import HTTPException, Request
from fastapi import status as http_status

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


def test_client_ip_prefers_forwarded_header():
    """Atras do proxy do Render, host e o IP do proxy; o real vem no XFF."""
    request = make_request(ip="10.10.0.5", forwarded="203.0.113.7, 10.10.0.5")

    assert deps.client_ip(request) == "203.0.113.7"


def test_client_ip_falls_back_to_connection_host():
    request = make_request(ip="192.168.1.9", forwarded=None)

    assert deps.client_ip(request) == "192.168.1.9"


async def test_login_limit_blocks_after_max_attempts(monkeypatch):
    monkeypatch.setattr(deps, "login_rate_limiter", deps.RateLimiter(max_requests=3, window_seconds=60))
    request = make_request(forwarded="203.0.113.7")

    for _ in range(3):
        await deps.login_rate_limit_dependency(request)

    with pytest.raises(HTTPException) as exc:
        await deps.login_rate_limit_dependency(request)

    assert exc.value.status_code == http_status.HTTP_429_TOO_MANY_REQUESTS


async def test_login_limit_is_per_ip(monkeypatch):
    """Um IP chutando senha nao derruba o login de todo mundo."""
    monkeypatch.setattr(deps, "login_rate_limiter", deps.RateLimiter(max_requests=1, window_seconds=60))
    noisy = make_request(forwarded="203.0.113.7")
    other = make_request(forwarded="198.51.100.20")

    await deps.login_rate_limit_dependency(noisy)
    with pytest.raises(HTTPException):
        await deps.login_rate_limit_dependency(noisy)

    # Outro cliente continua entrando normalmente.
    await deps.login_rate_limit_dependency(other)


async def test_general_limit_is_per_ip(monkeypatch):
    monkeypatch.setattr(deps, "rate_limiter", deps.RateLimiter(max_requests=1, window_seconds=60))
    first = make_request(forwarded="203.0.113.7")
    other = make_request(forwarded="198.51.100.20")

    await deps.rate_limit_dependency(first)
    with pytest.raises(HTTPException):
        await deps.rate_limit_dependency(first)

    await deps.rate_limit_dependency(other)
