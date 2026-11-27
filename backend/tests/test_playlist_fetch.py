import json

import httpx
import pytest

from app.services import playlist_fetch

M3U = b"#EXTM3U\n#EXTINF:-1,Teste\nhttps://example.com/live.m3u8\n"
NGINX = b"<!DOCTYPE html><html><head><title>Welcome to nginx!</title></head></html>"


def _transport(handler):
    return httpx.MockTransport(handler)


@pytest.fixture(autouse=True)
def _public_urls(monkeypatch):
    monkeypatch.setattr(playlist_fetch, "url_publica", lambda url: True)
    playlist_fetch._ip_cache.clear()
    playlist_fetch._doh_cache.clear()
    playlist_fetch._route_cache.clear()


@pytest.mark.asyncio
async def test_https_fallback_when_http_returns_nginx():
    seen = []

    def handler(request):
        seen.append(str(request.url))
        if request.url.scheme == "https":
            return httpx.Response(200, content=M3U, headers={"content-type": "audio/x-mpegurl"})
        return httpx.Response(200, content=NGINX, headers={"content-type": "text/html"})

    result = await playlist_fetch.fetch_playlist(
        "http://provider.example/get.php?username=user&password=secret",
        {},
        transport=_transport(handler),
        allow_helpers=False,
    )

    assert result.ok
    assert result.content == M3U
    assert result.strategy == "https alternativo"
    assert len(seen) == 2
    assert "username" not in json.dumps([a.to_dict() for a in result.attempts])
    assert "password" not in json.dumps([a.to_dict() for a in result.attempts])


@pytest.mark.asyncio
async def test_ip_fallback_keeps_host_header(monkeypatch):
    requests = []

    async def fake_system_ips(host, port):
        return ["93.184.216.34"]

    monkeypatch.setattr(playlist_fetch, "_system_ips", fake_system_ips)

    def handler(request):
        requests.append(request)
        if request.url.host == "93.184.216.34":
            assert request.headers["host"] == "provider.example"
            return httpx.Response(200, content=M3U, headers={"content-type": "audio/x-mpegurl"})
        return httpx.Response(200, content=NGINX, headers={"content-type": "text/html"})

    result = await playlist_fetch.fetch_playlist(
        "http://provider.example/get.php?username=user&password=secret",
        {},
        transport=_transport(handler),
    )

    assert result.ok
    assert result.strategy == "DNS do Render (http por IP)"
    assert any(request.url.host == "93.184.216.34" for request in requests)
    assert "93.184.216.34" in result.resolved_ips


@pytest.mark.asyncio
async def test_doh_fallback_used_when_dns_returns_nginx(monkeypatch):
    async def fake_system_ips(host, port):
        return ["93.184.216.34"]

    async def fake_doh_ips(host):
        return ["45.134.142.152"]

    async def fake_api(url, headers, *, transport):
        return [], None

    monkeypatch.setattr(playlist_fetch, "_system_ips", fake_system_ips)
    monkeypatch.setattr(playlist_fetch, "_doh_ips", fake_doh_ips)
    monkeypatch.setattr(playlist_fetch, "_alternate_api_hosts", fake_api)

    def handler(request):
        if request.url.host == "45.134.142.152":
            return httpx.Response(200, content=M3U, headers={"content-type": "audio/x-mpegurl"})
        return httpx.Response(200, content=NGINX, headers={"content-type": "text/html"})

    result = await playlist_fetch.fetch_playlist(
        "http://provider.example/get.php?username=user&password=secret",
        {},
        transport=_transport(handler),
    )

    assert result.ok
    assert result.strategy == "DoH (http por IP)"
    assert result.resolved_ips == ["93.184.216.34", "45.134.142.152"]


@pytest.mark.asyncio
async def test_playlist_over_size_limit_is_rejected():
    big = b"#EXTM3U\n" + (b"#EXTINF:-1,Canal\nhttps://example.com/a.m3u8\n" * 80)

    def handler(request):
        return httpx.Response(200, content=big, headers={"content-type": "audio/x-mpegurl"})

    result = await playlist_fetch.fetch_playlist(
        "http://provider.example/get.php",
        {},
        max_bytes=1024,
        transport=_transport(handler),
        allow_helpers=False,
    )

    assert not result.ok
    assert "playlist muito grande" in result.error_summary()
    assert "provider.example" not in result.error_summary()


@pytest.mark.asyncio
async def test_probe_reports_safe_diagnostics(monkeypatch):
    async def fake_system_ips(host, port):
        return []

    async def fake_doh_ips(host):
        return []

    async def fake_api(url, headers, *, transport):
        return [], None

    monkeypatch.setattr(playlist_fetch, "_system_ips", fake_system_ips)
    monkeypatch.setattr(playlist_fetch, "_doh_ips", fake_doh_ips)
    monkeypatch.setattr(playlist_fetch, "_alternate_api_hosts", fake_api)

    def handler(request):
        return httpx.Response(200, content=NGINX, headers={"content-type": "text/html"})

    result = await playlist_fetch.probe_playlist(
        "http://provider.example/get.php?username=user&password=secret",
        transport=_transport(handler),
    )

    payload = json.dumps(result)
    assert result["state"] == "error"
    assert "Welcome to nginx" in result["first_line"]
    assert "username" not in payload
    assert "password" not in payload
    assert "provider.example" not in payload
