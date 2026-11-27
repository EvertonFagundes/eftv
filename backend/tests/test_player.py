from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient

from app.config import settings
from app.database import get_db
from app.routes import player
from app.routes.player import router
from app.security.dependencies import get_current_active_subscription
from app.services.devices import DeviceLimitError
from app.services.playlist_cache import CacheInfo

DEVICE_HEADERS = {
    "X-Device-Id": "test-device-0001",
    "X-Device-Name": "Aparelho de teste",
}


class FakeSubscription:
    def __init__(self, days: int = 20) -> None:
        self.id = "sub-1"
        self.user_id = "user-1"
        self.status = "active"
        self.current_period_end = datetime.now(UTC) + timedelta(days=days)
        # Sem linha propria no provedor: usa a playlist compartilhada.
        self.provider_playlist_url = None
        self.provider_revoked_at = None


async def fake_db():
    yield object()


def build_client(days: int = 20) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_active_subscription] = lambda: FakeSubscription(days)
    app.dependency_overrides[get_db] = fake_db
    return TestClient(app)


@pytest.fixture
def client(monkeypatch) -> TestClient:
    async def noop_bind(*args, **kwargs):
        return None

    monkeypatch.setattr("app.routes.player.bind_device", noop_bind)
    return build_client()


def test_playlist_access_returns_configured_source(client, monkeypatch):
    monkeypatch.setattr(settings, "IPTV_PLAYLIST_URL", "https://provider.example/list.m3u")
    monkeypatch.setattr(settings, "IPTV_PLAYLIST_USER_AGENT", "VLC/3.0.20 LibVLC/3.0.20")
    monkeypatch.setattr(settings, "IPTV_PLAYLIST_REFERER", None)

    response = client.get("/player/playlist", headers=DEVICE_HEADERS)

    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["playlist_url"] == "https://provider.example/list.m3u"
    assert body["user_agent"] == "VLC/3.0.20 LibVLC/3.0.20"
    assert body["refresh_in"] == settings.IPTV_PLAYLIST_REFRESH_SECONDS
    assert body["offline_grace_seconds"] == settings.OFFLINE_GRACE_MINUTES * 60
    assert body["subscription"]["status"] == "active"
    assert body["subscription"]["days_remaining"] >= 19


def test_playlist_requires_device_id(client, monkeypatch):
    monkeypatch.setattr(settings, "IPTV_PLAYLIST_URL", "https://provider.example/list.m3u")

    response = client.get("/player/playlist")

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["detail"]["code"] == "device_id_missing"


def test_playlist_rejects_when_device_limit_reached(monkeypatch):
    async def deny_bind(*args, **kwargs):
        raise DeviceLimitError()

    monkeypatch.setattr("app.routes.player.bind_device", deny_bind)
    monkeypatch.setattr(settings, "IPTV_PLAYLIST_URL", "https://provider.example/list.m3u")

    response = build_client().get("/player/playlist", headers=DEVICE_HEADERS)

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["detail"]["code"] == "device_limit"


def test_playlist_not_configured_returns_503(client, monkeypatch):
    monkeypatch.setattr(settings, "IPTV_PLAYLIST_URL", "")

    response = client.get("/player/playlist", headers=DEVICE_HEADERS)

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE


def test_playlist_requires_active_subscription():
    app = FastAPI()
    app.include_router(router)

    def deny():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Assinatura expirada ou cancelada",
        )

    app.dependency_overrides[get_current_active_subscription] = deny

    response = TestClient(app).get("/player/playlist", headers=DEVICE_HEADERS)

    assert response.status_code == status.HTTP_403_FORBIDDEN


class FakeDB:
    async def commit(self) -> None:
        return None


def build_trial_client(subscription, monkeypatch):
    async def noop_bind(*args, **kwargs):
        return None

    monkeypatch.setattr("app.routes.player.bind_device", noop_bind)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_active_subscription] = lambda: subscription
    app.dependency_overrides[get_db] = lambda: FakeDB()
    return TestClient(app)


def test_playlist_revokes_trial_when_device_used_elsewhere(monkeypatch):
    """Fecha o caminho de quem confirma o e-mail pelo navegador."""
    monkeypatch.setattr(settings, "IPTV_PLAYLIST_URL", "https://provider.example/list.m3u")

    async def already_used(db, device_id, user_id):
        return True

    revoked = {}

    def fake_revoke(subscription):
        revoked["done"] = True
        subscription.status = "cancelled"

    monkeypatch.setattr("app.routes.player.trials.device_already_used", already_used)
    monkeypatch.setattr("app.routes.player.trials.revoke_trial", fake_revoke)

    subscription = FakeSubscription()
    subscription.status = "trial"
    client = build_trial_client(subscription, monkeypatch)

    response = client.get("/player/playlist", headers=DEVICE_HEADERS)

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["detail"]["code"] == "trial_device_used"
    assert revoked["done"] is True


def test_playlist_claims_device_on_valid_trial(monkeypatch):
    monkeypatch.setattr(settings, "IPTV_PLAYLIST_URL", "https://provider.example/list.m3u")
    async def not_used(db, device_id, user_id):
        return False

    claimed = {}

    async def fake_claim(db, **kwargs):
        claimed.update(kwargs)

    monkeypatch.setattr("app.routes.player.trials.device_already_used", not_used)
    monkeypatch.setattr("app.routes.player.trials.claim", fake_claim)

    subscription = FakeSubscription()
    subscription.status = "trial"
    client = build_trial_client(subscription, monkeypatch)

    response = client.get("/player/playlist", headers=DEVICE_HEADERS)

    assert response.status_code == status.HTTP_200_OK
    assert claimed["device_id"] == DEVICE_HEADERS["X-Device-Id"]
    assert claimed["user_id"] == subscription.user_id


def test_playlist_prefers_the_subscriber_own_provider_line(client, monkeypatch):
    """Linha propria permite revogar um cliente sem trocar a de todos."""
    monkeypatch.setattr(settings, "IPTV_PLAYLIST_URL", "https://provider.example/shared.m3u")

    subscription = FakeSubscription()
    subscription.provider_playlist_url = "https://provider.example/linha-do-cliente.m3u"
    client.app.dependency_overrides[get_current_active_subscription] = lambda: subscription

    response = client.get("/player/playlist", headers=DEVICE_HEADERS)

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["playlist_url"] == "https://provider.example/linha-do-cliente.m3u"


def test_playlist_ignores_a_revoked_provider_line(client, monkeypatch):
    monkeypatch.setattr(settings, "IPTV_PLAYLIST_URL", "https://provider.example/shared.m3u")

    from datetime import UTC, datetime

    subscription = FakeSubscription()
    subscription.provider_playlist_url = "https://provider.example/linha-revogada.m3u"
    subscription.provider_revoked_at = datetime.now(UTC)
    client.app.dependency_overrides[get_current_active_subscription] = lambda: subscription

    response = client.get("/player/playlist", headers=DEVICE_HEADERS)

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["playlist_url"] == "https://provider.example/shared.m3u"


def test_playlist_detection_accepts_m3u_with_bom_or_extinf():
    assert player._parece_playlist_m3u(b"\xef\xbb\xbf\n#EXTM3U\n#EXTINF:-1,Teste\n")
    assert player._parece_playlist_m3u(b"#EXTINF:-1,Teste\nhttps://example/stream\n")
    assert not player._parece_playlist_m3u(b"<!DOCTYPE html><html>nginx</html>")


def test_playlist_text_falls_back_to_shared_when_own_line_is_html(monkeypatch):
    """Linha propria quebrada nao pode impedir o fallback do backend."""
    monkeypatch.setattr(settings, "IPTV_PLAYLIST_URL", "https://provider.example/shared.m3u")
    subscription = FakeSubscription()
    subscription.provider_playlist_url = "https://provider.example/own.m3u"
    client = build_client()
    client.app.dependency_overrides[get_current_active_subscription] = lambda: subscription

    chamadas: list[str] = []

    async def fake_download(url, headers):
        chamadas.append(url)
        if "own" in url:
            return b"<!DOCTYPE html><html><title>Welcome to nginx!</title></html>"
        return b"#EXTM3U\n#EXTINF:-1,Teste\nhttps://example/stream\n"

    monkeypatch.setattr(player, "_baixar_playlist", fake_download)

    response = client.get("/player/playlist-text", headers=DEVICE_HEADERS)

    assert response.status_code == status.HTTP_200_OK
    assert response.content.startswith(b"#EXTM3U")
    assert chamadas == [
        "https://provider.example/own.m3u",
        "https://provider.example/shared.m3u",
    ]


def test_playlist_text_reports_both_invalid_without_leaking_urls(monkeypatch):
    monkeypatch.setattr(settings, "IPTV_PLAYLIST_URL", "https://provider.example/shared.m3u")
    subscription = FakeSubscription()
    subscription.provider_playlist_url = "https://provider.example/own.m3u"
    client = build_client()
    client.app.dependency_overrides[get_current_active_subscription] = lambda: subscription

    async def fake_download(url, headers):
        return b"<!DOCTYPE html><html><title>Welcome to nginx!</title></html>"

    async def no_cache(db):
        return None

    monkeypatch.setattr(player, "_baixar_playlist", fake_download)
    monkeypatch.setattr(player, "load_cached_playlist", no_cache)

    response = client.get("/player/playlist-text", headers=DEVICE_HEADERS)

    assert response.status_code == status.HTTP_502_BAD_GATEWAY
    detail = response.json()["detail"]
    assert "linha do assinante" in detail
    assert "playlist compartilhada" in detail
    assert "provider.example" not in detail
    assert "nginx" not in detail


def test_playlist_text_uses_cache_when_provider_is_blocked(monkeypatch):
    monkeypatch.setattr(settings, "IPTV_PLAYLIST_URL", "https://provider.example/shared.m3u")
    client = build_client()

    async def fake_download(url, headers):
        raise player.PlaylistFetchError("bloqueado")

    info = CacheInfo(
        updated_at=datetime.now(UTC),
        size_bytes=32,
        compressed_bytes=24,
        sha256="a" * 64,
        source="upload",
    )
    cached_m3u = b"#EXTM3U\n#EXTINF:-1,Teste\nhttps://example/stream\n"

    async def fake_cache(db):
        return cached_m3u, info

    monkeypatch.setattr(player, "_baixar_playlist", fake_download)
    monkeypatch.setattr(player, "load_cached_playlist", fake_cache)

    response = client.get("/player/playlist-text", headers=DEVICE_HEADERS)

    assert response.status_code == status.HTTP_200_OK
    assert response.content == cached_m3u
    assert response.headers["x-playlist-source"] == "cache"
    assert response.headers["x-playlist-cache-age"] == "0"


def test_playlist_text_prefers_valid_own_line(monkeypatch):
    monkeypatch.setattr(settings, "IPTV_PLAYLIST_URL", "https://provider.example/shared.m3u")
    subscription = FakeSubscription()
    subscription.provider_playlist_url = "https://provider.example/own.m3u"
    client = build_client()
    client.app.dependency_overrides[get_current_active_subscription] = lambda: subscription

    chamadas: list[str] = []

    async def fake_download(url, headers):
        chamadas.append(url)
        return b"#EXTM3U\n#EXTINF:-1,Teste\nhttps://example/stream\n"

    monkeypatch.setattr(player, "_baixar_playlist", fake_download)

    response = client.get("/player/playlist-text", headers=DEVICE_HEADERS)

    assert response.status_code == status.HTTP_200_OK
    assert chamadas == ["https://provider.example/own.m3u"]


def test_playlist_text_without_configuration_returns_503(client, monkeypatch):
    monkeypatch.setattr(settings, "IPTV_PLAYLIST_URL", "")

    response = client.get("/player/playlist-text", headers=DEVICE_HEADERS)

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
