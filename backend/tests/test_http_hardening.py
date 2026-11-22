# tests/test_http_hardening.py - Limite de corpo e cabecalhos de seguranca
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.security.middleware import BodySizeLimitMiddleware, SecurityHeadersMiddleware


def build_app(max_bytes: int = 64) -> FastAPI:
    app = FastAPI()

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    @app.get("/docs")
    async def docs():
        return {"ok": True}

    @app.post("/echo")
    async def echo(payload: dict):
        return payload

    app.add_middleware(BodySizeLimitMiddleware, max_bytes=max_bytes)
    app.add_middleware(SecurityHeadersMiddleware)
    return app


def test_security_headers_are_added():
    client = TestClient(build_app())

    response = client.get("/ping")

    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["permissions-policy"].startswith("camera=()")
    assert "default-src 'none'" in response.headers["content-security-policy"]


def test_docs_page_keeps_its_own_csp():
    """Swagger/ReDoc precisam carregar JS; o CSP restritivo quebraria a tela."""
    client = TestClient(build_app())

    response = client.get("/docs")

    assert "content-security-policy" not in response.headers


def test_hsts_only_on_https():
    http_client = TestClient(build_app())
    https_client = TestClient(build_app(), base_url="https://testserver")

    assert "strict-transport-security" not in http_client.get("/ping").headers
    assert "strict-transport-security" in https_client.get("/ping").headers


def test_body_with_content_length_over_limit_is_rejected():
    client = TestClient(build_app(max_bytes=64))

    response = client.post("/echo", json={"data": "x" * 100})

    assert response.status_code == 413
    assert "muito grande" in response.json()["detail"]


def test_chunked_body_over_limit_is_rejected():
    """Sem Content-Length o limite tambem precisa valer.

    O FastAPI converte a leitura interrompida em 400 ao parsear o JSON; o
    importante e o corpo nao ser processado por inteiro.
    """
    client = TestClient(build_app(max_bytes=64))

    response = client.post(
        "/echo",
        content=iter([b'{"data":"', b"x" * 80, b'"}`']),
        headers={"content-type": "application/json"},
    )

    assert response.status_code in (400, 413)


def test_body_within_limit_is_accepted():
    client = TestClient(build_app(max_bytes=1024))

    response = client.post("/echo", json={"data": "ok"})

    assert response.status_code == 200
    assert response.json() == {"data": "ok"}
