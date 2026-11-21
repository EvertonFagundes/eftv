# tests/test_server_hardening.py - Proxy local e mascaramento de URLs
import importlib.util
import socket
from pathlib import Path

import pytest

SERVER_PATH = Path(__file__).resolve().parents[2] / "server.py"
spec = importlib.util.spec_from_file_location("eftv_server", SERVER_PATH)
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


def test_playlist_url_is_masked_for_the_api():
    """A URL da playlist e uma credencial: nao pode sair crua na API."""
    masked = server.mascarar_url(
        "http://cliente:segredo@provedor.example/live/u/p/1.ts?username=abc&password=xyz&x=1"
    )

    assert "segredo" not in masked
    assert "cliente:" not in masked
    assert "abc" not in masked
    assert "xyz" not in masked
    assert "provedor.example" in masked
    assert masked.endswith("x=1")


def test_playlist_summary_uses_the_masked_url():
    summary = server.summarize(
        {
            "id": "1",
            "name": "Minha lista",
            "url": "http://user:pass@provedor.example/list.m3u?token=abc",
            "channels": [],
        }
    )

    assert "pass" not in summary["url"]
    assert "abc" not in summary["url"]


def test_proxy_blocks_loopback_and_private_targets():
    assert server.proxy_alvo_permitido("http://127.0.0.1:8124/admin") is False
    assert server.proxy_alvo_permitido("http://10.0.0.5/canal") is False
    assert server.proxy_alvo_permitido("http://169.254.169.254/latest/meta-data") is False
    assert server.proxy_alvo_permitido("http://localhost:8080/") is False


def test_proxy_allows_a_public_host(monkeypatch):
    def fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(server.socket, "getaddrinfo", fake_getaddrinfo)

    assert server.proxy_alvo_permitido("https://provedor.example/live.m3u8") is True


@pytest.mark.parametrize(
    "url",
    ["file:///etc/passwd", "ftp://provedor.example/x", "javascript:alert(1)"],
)
def test_proxy_rejects_non_http_schemes(url):
    assert server.proxy_alvo_permitido(url) is False
